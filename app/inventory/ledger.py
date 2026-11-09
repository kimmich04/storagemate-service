"""Ghi sổ phiếu regex: từng dòng một, quy về ĐVT gốc, chặn tồn âm. Chỉ INSERT inventory_log.

Dòng không ghi được thì trả về kèm lý do để bot báo nhân viên gõ lại (spec 2026-11-06 mục 7).
Không commit — transaction do worker giữ.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from functools import cache
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.inventory.models import InventoryLog
from app.items.models import Item
from app.parser.catalog import CatalogItem, ResolvedLine, load_catalog, resolve
from app.parser.normalize import fold
from app.parser.regex import UNKNOWN_LOC, Phieu
from app.staff.models import Location, Staff

logger = logging.getLogger(__name__)

LOCAL_TZ = ZoneInfo(settings.TZ)
MAX_BACKDATE = timedelta(days=7)
ROUTE_DONE, ROUTE_PARTIAL, ROUTE_REJECTED = "phieu", "phieu_partial", "phieu_rejected"

REASON_UNKNOWN = "không tìm thấy món trong danh mục"
REASON_UNIT = "chưa quy đổi được đơn vị"
REASON_BAD_LINE = "không đọc được dòng này"
REASON_ZERO = "số lượng phải lớn hơn 0"
REASON_NOT_IN_DB = "món chưa có trong danh mục DB"


@dataclass(frozen=True)
class Skipped:
    raw: str
    reason: str


@dataclass(frozen=True)
class LedgerResult:
    written: int
    total: int
    skipped: list[Skipped] = field(default_factory=list)
    date_error: str | None = None

    @property
    def route(self) -> str:
        if self.written == 0:
            return ROUTE_REJECTED
        return ROUTE_PARTIAL if self.skipped else ROUTE_DONE


@dataclass(frozen=True)
class _Part:
    item: Item
    qty: Decimal  # như nhân viên gõ (thành phần bộ: = qty_base)
    unit: str
    qty_base: Decimal


def record(
    session: Session,
    phieu: Phieu,
    *,
    staff: Staff,
    inbound_id: int | None,
    raw_message: str | None,
    sent_at: datetime,
    now: datetime,
    source: str = "regex",
) -> LedgerResult:
    total = len(phieu.lines) + len(phieu.bad_lines)
    event_time = _event_time(phieu, sent_at)
    if error := _date_error(event_time, now):
        return LedgerResult(written=0, total=total, date_error=error)

    items = _items_by_code(session, staff.tenant_id)
    counterpart = _counterpart(session, staff.tenant_id, phieu)
    stock: dict[int, Decimal] = {}
    skipped = [Skipped(raw, REASON_BAD_LINE) for raw in phieu.bad_lines]
    written = 0
    for resolved in map(resolve, phieu.lines):
        parts, reason = _parts(resolved, items)
        if reason is None and phieu.action == "OUT":
            reason = _take_stock(session, stock, staff.default_location_id, parts)
        if reason is not None:
            skipped.append(Skipped(resolved.line.raw, reason))
            continue
        note = "; ".join(n for n in (resolved.line.note, phieu.date_note) if n) or None
        for part in parts:
            session.add(
                _row(phieu, part, staff, counterpart, event_time, inbound_id, raw_message, note, source)
            )
        written += 1
    session.flush()
    return LedgerResult(written=written, total=total, skipped=skipped)


def _event_time(phieu: Phieu, sent_at: datetime) -> datetime:
    """Ngày ghi trong phiếu + giờ nhận tin (giờ địa phương)."""
    clock = sent_at.astimezone(LOCAL_TZ).time()
    return datetime.combine(phieu.date, clock, tzinfo=LOCAL_TZ)


def _date_error(event_time: datetime, now: datetime) -> str | None:
    if event_time > now:
        return f"ngày {event_time:%d/%m} ở tương lai"
    if event_time < now - MAX_BACKDATE:
        return f"ngày {event_time:%d/%m} đã quá 7 ngày"
    return None


def _items_by_code(session: Session, tenant_id: int) -> dict[str, Item]:
    rows = session.scalars(select(Item).where(Item.tenant_id == tenant_id, Item.code.is_not(None)))
    return {item.code: item for item in rows}


def _counterpart(session: Session, tenant_id: int, phieu: Phieu) -> int | None:
    """Nơi gửi/nhận bên kia; không khớp tên kho nào → NULL (chữ gốc vẫn nằm trong raw_message)."""
    name = phieu.to_loc if phieu.action == "OUT" else phieu.from_loc
    if name == UNKNOWN_LOC:
        return None
    wanted = fold(name)
    for location in session.scalars(select(Location).where(Location.tenant_id == tenant_id)):
        if wanted == fold(location.name) or wanted in {fold(alias) for alias in location.aliases}:
            return location.id
    return None


def _parts(resolved: ResolvedLine, items: dict[str, Item]) -> tuple[list[_Part], str | None]:
    line, item = resolved.line, resolved.item
    if resolved.status != "ok" or item is None:  # unknown không có warning → REASON_UNKNOWN
        return [], resolved.warning or REASON_UNKNOWN
    if resolved.qty_base is None or resolved.base_unit != item.base_unit:
        return [], resolved.warning or REASON_UNIT
    if line.qty <= 0:
        return [], REASON_ZERO
    if resolved.components:
        wanted = [(_catalog_by_name()[name], qty) for name, qty in resolved.components]
    else:
        wanted = [(item, resolved.qty_base)]
    missing = [catalog.code for catalog, _ in wanted if catalog.code not in items]
    if missing:
        logger.warning("Mã catalog %s chưa có trong bảng items — chạy scripts/import_opening.py", missing)
        return [], REASON_NOT_IN_DB
    if resolved.components:
        parts = [_Part(items[c.code], qty, c.base_unit, qty) for c, qty in wanted]
    else:
        parts = [_Part(items[item.code], line.qty, line.unit or item.base_unit, resolved.qty_base)]
    return parts, None


@cache
def _catalog_by_name() -> dict[str, CatalogItem]:
    return {item.name: item for item in load_catalog()}


def _take_stock(
    session: Session, stock: dict[int, Decimal], location_id: int, parts: list[_Part]
) -> str | None:
    """Trừ tồn dần theo thứ tự dòng; một thành phần thiếu → cả dòng bị trả lại, tồn không đổi."""
    for part in parts:
        if part.item.id not in stock:
            stock[part.item.id] = _current_stock(session, location_id, part.item.id)
    needed: dict[int, Decimal] = {}
    for part in parts:
        needed[part.item.id] = needed.get(part.item.id, Decimal(0)) + part.qty_base
    for part in parts:
        available = stock[part.item.id]
        if needed[part.item.id] > available:
            unit = part.item.base_unit.lower()
            return (
                f"tồn {part.item.name} chỉ còn {_number(available)} {unit}, "
                f"không thể xuất {_number(needed[part.item.id])} {unit}"
            )
    for item_id, qty in needed.items():
        stock[item_id] -= qty
    return None


def _current_stock(session: Session, location_id: int, item_id: int) -> Decimal:
    """= view current_stock: SUM(delta_base) theo (item, kho)."""
    total = session.scalar(
        select(func.coalesce(func.sum(InventoryLog.delta_base), 0)).where(
            InventoryLog.location_id == location_id, InventoryLog.item_id == item_id
        )
    )
    return Decimal(total)


def _row(
    phieu: Phieu,
    part: _Part,
    staff: Staff,
    counterpart: int | None,
    event_time: datetime,
    inbound_id: int | None,
    raw_message: str | None,
    note: str | None,
    source: str,
) -> InventoryLog:
    sign = 1 if phieu.action == "IN" else -1
    return InventoryLog(
        tenant_id=staff.tenant_id,
        location_id=staff.default_location_id,
        item_id=part.item.id,
        action=phieu.action,
        qty=part.qty,
        unit=part.unit,
        qty_base=part.qty_base,
        delta_base=sign * part.qty_base,
        counterpart_location_id=counterpart,
        event_time=event_time,
        staff_id=staff.id,
        inbound_id=inbound_id,
        raw_message=raw_message,
        parser_source=source,
        note=note,
    )


def _number(qty: Decimal) -> str:
    return f"{qty.normalize():f}".replace(".", ",")
