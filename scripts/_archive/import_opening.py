"""Dựng DB dev: tenant, kho, danh mục + loại hàng, tồn đầu kỳ từ Excel T10, gắn nhân viên, dữ liệu ảo.

Chạy (DB dev, DATABASE_URL trong settings):
  python scripts/import_opening.py <file Excel T10> [--dry-run]
  python scripts/import_opening.py --link-staff "Nash" <zalo_chat_id>
  python scripts/import_opening.py --fake-moves [--seed 1]
  python scripts/import_opening.py --reset <file Excel T10>      # chỉ khi DB ở localhost

Tồn đầu kỳ = cột "Tồn cuối 31.10" của sheet đầu tiên, ghi thành dòng ADJUST/opening lúc 31/10 23:59:59.
Loại hàng = dòng tiêu đề nhóm (cột A trống, cột B có chữ) gần nhất phía trên mỗi mặt hàng.
"""

import argparse
import random
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

import openpyxl
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.auth.models import Admin
from app.config import settings
from app.database import SessionLocal, engine
from app.inventory.models import InventoryLog
from app.items.models import Item, Unit
from app.items.service import db_names
from app.parser.catalog import load_catalog
from app.parser.normalize import fold
from app.staff.models import Location, Staff, Tenant

LOCAL_TZ = ZoneInfo(settings.TZ)
TENANT_NAME = "Kho tổng SG"
IMPORT_ADMIN_EMAIL = "import@storagemate.local"
NO_LOGIN_HASH = "!"  # không khớp hash nào → không đăng nhập được
OPENING_AT = datetime(2026, 10, 31, 23, 59, 59, tzinfo=LOCAL_TZ)
OPENING_NOTE = "Tồn cuối 31.10 (Excel T10)"
FAKE_NOTE = "DỮ LIỆU ẢO (dev)"
FAKE_START = date(2026, 11, 1)
FAKE_ITEMS_PER_DAY = 5
FAKE_MAX_QTY = 20
FIRST_DATA_ROW = 3
CODE_COL, NAME_COL, UNIT_COL, CLOSING_COL = 0, 1, 2, 8  # A, B, C, I ("Tồn cuối 31.10")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

# (code, tên, loại, alias đã fold) — khớp LOCATION_ALIASES của parser và sheet xuất của Excel
LOCATIONS = [
    ("KT", "kho tổng", "warehouse", ["kho tong", "khi tong"]),
    ("K220", "kho 220", "branch", ["220", "kho 220"]),
    ("PQ", "Phú Quốc", "branch", ["pq", "phu quoc"]),
    ("DT", "đối tác / nội bộ", "partner", ["doi tac", "noi bo", "dinh"]),
]


@dataclass(frozen=True)
class OpeningRow:
    code: str
    name: str
    unit: str
    qty: Decimal | None
    category: str | None


def read_opening(xlsx: Path) -> list[OpeningRow]:
    sheet = openpyxl.load_workbook(xlsx, read_only=True, data_only=True).worksheets[0]
    rows, category = [], None
    for values in sheet.iter_rows(min_row=FIRST_DATA_ROW, values_only=True):
        code, name = values[CODE_COL], values[NAME_COL]
        if code is None and isinstance(name, str) and name.strip():
            category = name.strip()
            continue
        if not isinstance(code, int | float):
            continue
        rows.append(
            OpeningRow(
                code=str(int(code)),
                name=str(name or "").strip(),
                unit=str(values[UNIT_COL] or "").strip(),
                qty=_decimal(values[CLOSING_COL]),
                category=category,
            )
        )
    return rows


def _decimal(value: object) -> Decimal | None:
    try:
        return None if value is None else Decimal(str(value))
    except InvalidOperation:
        return None


def import_all(session: Session, rows: list[OpeningRow]) -> list[str]:
    """Trả danh sách cảnh báo (mã lạ, đơn vị lệch, tồn âm/không đọc được)."""
    if session.scalar(select(func.count()).select_from(Tenant)):
        raise SystemExit("DB đã có tenant — dùng --reset trên DB dev nếu muốn nạp lại.")
    tenant = Tenant(name=TENANT_NAME)
    session.add(tenant)
    session.flush()
    locations = [Location(tenant_id=tenant.id, code=c, name=n, kind=k, aliases=a) for c, n, k, a in LOCATIONS]
    session.add_all(locations)
    admin = Admin(
        tenant_id=tenant.id, email=IMPORT_ADMIN_EMAIL, name="Nhập liệu", password_hash=NO_LOGIN_HASH
    )
    session.add(admin)
    session.flush()
    by_code = {row.code: row for row in rows}
    items = _import_items(session, tenant.id, by_code)
    return _import_opening_stock(session, tenant.id, locations[0].id, admin.id, rows, items)


def _import_items(session: Session, tenant_id: int, by_code: dict[str, OpeningRow]) -> dict[str, Item]:
    items: dict[str, Item] = {}
    names = db_names(load_catalog())
    for entry in load_catalog():
        excel = by_code.get(entry.code)
        item = Item(
            tenant_id=tenant_id,
            code=entry.code,
            name=names[entry.code],
            base_unit=entry.base_unit,
            category=excel.category if excel else None,
        )
        session.add(item)
        items[entry.code] = item
    session.flush()
    for entry in load_catalog():
        session.add_all(
            Unit(item_id=items[entry.code].id, unit_name=unit, factor=factor)
            for unit, factor in entry.conversions.items()
            if factor is not None
        )
    return items


def _import_opening_stock(
    session: Session, tenant_id: int, location_id: int, admin_id: int, rows: list[OpeningRow], items: dict
) -> list[str]:
    warnings = []
    for row in rows:
        item = items.get(row.code)
        if item is None:
            warnings.append(f"Mã {row.code} «{row.name}» không có trong catalog — bỏ qua")
        elif row.qty is None or row.qty < 0:
            warnings.append(f"Mã {row.code} «{row.name}»: tồn «{row.qty}» không hợp lệ — bỏ qua")
        elif row.unit and fold(row.unit) != fold(item.base_unit):
            warnings.append(f"Mã {row.code}: Excel ghi «{row.unit}», catalog «{item.base_unit}» — bỏ qua")
        elif row.qty > 0:
            session.add(_opening_row(tenant_id, location_id, admin_id, item, row.qty))
    session.flush()
    return warnings


def _opening_row(tenant_id: int, location_id: int, admin_id: int, item: Item, qty: Decimal) -> InventoryLog:
    return InventoryLog(
        tenant_id=tenant_id,
        location_id=location_id,
        item_id=item.id,
        action="ADJUST",
        qty=qty,
        unit=item.base_unit,
        qty_base=qty,
        delta_base=qty,
        event_time=OPENING_AT,
        admin_id=admin_id,
        parser_source="opening",
        note=OPENING_NOTE,
    )


def link_staff(session: Session, name: str, chat_id: str) -> Staff:
    """Thay mã mời trong Phase 1: gắn chat Zalo vào nhân viên của kho tổng (tạo mới nếu chưa có)."""
    tenant = session.scalars(select(Tenant)).first()
    if tenant is None:
        raise SystemExit("Chưa có tenant — chạy import Excel trước.")
    warehouse = session.scalars(select(Location).where(Location.code == "KT")).one()
    staff = session.scalars(select(Staff).where(Staff.zalo_chat_id == chat_id)).first()
    if staff is None:
        staff = Staff(tenant_id=tenant.id, default_location_id=warehouse.id, name=name)
        session.add(staff)
    staff.name, staff.zalo_chat_id, staff.linked_at = name, chat_id, datetime.now(LOCAL_TZ)
    session.flush()
    return staff


def fake_moves(session: Session, seed: int, end: date) -> int:
    """Cặp NHẬP q (sáng) + XUẤT q (chiều) cùng món mỗi ngày → tồn cuối ngày không đổi. Trả số dòng đã ghi."""
    if session.scalar(select(func.count()).select_from(InventoryLog).where(InventoryLog.note == FAKE_NOTE)):
        raise SystemExit("Đã có dữ liệu ảo — dùng --reset để làm lại.")
    admin = session.scalars(select(Admin).where(Admin.email == IMPORT_ADMIN_EMAIL)).one()
    warehouse = session.scalars(select(Location).where(Location.code == "KT")).one()
    others = list(session.scalars(select(Location.id).where(Location.code != "KT")))
    stocked = list(
        session.scalars(
            select(Item)
            .join(InventoryLog, InventoryLog.item_id == Item.id)
            .group_by(Item.id)
            .having(func.sum(InventoryLog.delta_base) > 0)
            .order_by(Item.id)
        )
    )
    rng = random.Random(seed)
    count = 0
    for day in _days(FAKE_START, end):
        for item in rng.sample(stocked, min(FAKE_ITEMS_PER_DAY, len(stocked))):
            qty = Decimal(rng.randint(1, FAKE_MAX_QTY))
            morning = datetime.combine(day, time(8, rng.randint(0, 59)), tzinfo=LOCAL_TZ)
            evening = datetime.combine(day, time(16, rng.randint(0, 59)), tzinfo=LOCAL_TZ)
            for action, at, sign, counterpart in (
                ("IN", morning, 1, None),
                ("OUT", evening, -1, rng.choice(others)),
            ):
                session.add(
                    InventoryLog(
                        tenant_id=item.tenant_id,
                        location_id=warehouse.id,
                        item_id=item.id,
                        action=action,
                        qty=qty,
                        unit=item.base_unit,
                        qty_base=qty,
                        delta_base=sign * qty,
                        counterpart_location_id=counterpart,
                        event_time=at,
                        admin_id=admin.id,
                        parser_source="manual",
                        note=FAKE_NOTE,
                    )
                )
                count += 1
    session.flush()
    return count


def _days(start: date, end: date) -> Iterator[date]:
    """Từ start tới hết hôm qua — giờ ảo của hôm nay có thể ở tương lai."""
    day = start
    while day < end:
        yield day
        day += timedelta(days=1)


def reset() -> None:
    """Xoá sạch DB dev (TRUNCATE được, trigger chỉ chặn UPDATE/DELETE). Từ chối nếu DB không ở máy này."""
    host = make_url(settings.DATABASE_URL).host
    if host not in LOCAL_HOSTS:
        raise SystemExit(f"--reset chỉ chạy trên DB localhost (đang trỏ {host}).")
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE tenants, inbound_messages RESTART IDENTITY CASCADE"))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("xlsx", nargs="?", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--link-staff", nargs=2, metavar=("TÊN", "CHAT_ID"))
    parser.add_argument("--fake-moves", action="store_true")
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args(argv)

    if args.reset:
        reset()
        print("Đã xoá sạch DB dev.")
    if args.xlsx:
        _run_import(args.xlsx, args.dry_run)
    if args.link_staff:
        with SessionLocal.begin() as session:
            staff = link_staff(session, *args.link_staff)
            print(f"Đã gắn chat {staff.zalo_chat_id} cho «{staff.name}».")
    if args.fake_moves:
        with SessionLocal.begin() as session:
            print(f"Đã ghi {fake_moves(session, args.seed, datetime.now(LOCAL_TZ).date())} dòng ảo.")
    if not (args.reset or args.xlsx or args.link_staff or args.fake_moves):
        parser.print_help()
    return 0


def _run_import(xlsx: Path, dry_run: bool) -> None:
    rows = read_opening(xlsx)
    groups = {row.category for row in rows}
    print(f"Excel: {len(rows)} mặt hàng, {len(groups)} nhóm: {', '.join(sorted(g or '?' for g in groups))}")
    session = SessionLocal()
    try:
        warnings = import_all(session, rows)
        for warning in warnings:
            print("⚠️", warning)
        if dry_run:
            session.rollback()
            print("--dry-run: không ghi gì.")
        else:
            session.commit()
            print("Đã nạp danh mục + tồn đầu kỳ.")
    finally:
        session.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # console Windows mặc định cp1252
    sys.exit(main(sys.argv[1:]))
