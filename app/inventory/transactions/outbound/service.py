"""Số liệu trang Xuất Kho: lượt xuất (dòng OUT) của kho tổng, SQL thuần như inbound/service.py. Chỉ đọc.

Bộ lọc nơi nhận (dùng chung O2..O6), xem `destination_filter`:
- không chọn gì (ids rỗng và unknown là None) → mọi nơi nhận, kể cả chưa rõ;
- có chọn → nơi nằm trong `ids`, và dòng chưa rõ nơi nhận khi `unknown` là True.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.inventory.counted_rows import COUNTED_ROWS, FROM_START, UPTO_END, base_params, escape_like
from app.inventory.dependencies import WarehouseScope
from app.inventory.period import Period
from app.paging import fetch_page

UNKNOWN_NAME = "Chưa rõ nơi nhận"
MAX_SERIES = 5  # số nơi nhận riêng lẻ ở biểu đồ (C); phần còn lại gộp "Khác"

_OUT_ROWS = f"{COUNTED_ROWS} AND l.action = 'OUT' AND {FROM_START} AND {UPTO_END}"


@dataclass(frozen=True)
class DestinationOption:
    id: int
    name: str
    kind: str
    count: int


@dataclass(frozen=True)
class DestinationsResult:
    destinations: list[DestinationOption]
    unknown_count: int | None


@dataclass(frozen=True)
class DestinationRow:
    id: int
    name: str
    kind: str
    count: int
    item_count: int
    last_date: date


@dataclass(frozen=True)
class UnknownRow:
    count: int
    item_count: int
    last_date: date


@dataclass(frozen=True)
class ByDestinationResult:
    destinations: list[DestinationRow]
    unknown: UnknownRow | None


@dataclass(frozen=True)
class Series:
    key: str
    name: str
    kind: str


@dataclass(frozen=True)
class Day:
    date: date
    total: int
    counts: dict[str, int]


@dataclass(frozen=True)
class DailyResult:
    series: list[Series]
    days: list[Day]


@dataclass(frozen=True)
class TopItem:
    item_id: int
    code: str | None
    name: str
    unit: str
    count: int
    qty_base: Decimal


@dataclass(frozen=True)
class OutTransaction:
    id: int
    item_id: int
    code: str | None
    name: str
    unit: str
    qty: Decimal
    event_date: date
    destination_id: int | None
    destination_name: str | None
    destination_kind: str | None


@dataclass(frozen=True)
class OutTransactionPage:
    total: int
    rows: list[OutTransaction]


def destination_filter(ids: list[int] | None, unknown: bool | None, params: dict[str, object]) -> str:
    """Điều kiện SQL lọc nơi nhận (bắt đầu bằng " AND ", rỗng nếu lấy tất cả); thêm bind vào `params`."""
    if not ids and unknown is None:
        return ""
    conds = []
    if ids:
        conds.append("l.counterpart_location_id = ANY(CAST(:dest_ids AS bigint[]))")
        params["dest_ids"] = ids
    if unknown:
        conds.append("l.counterpart_location_id IS NULL")
    return f" AND ({' OR '.join(conds)})" if conds else " AND FALSE"  # có chọn nhưng không nơi nào


def out_destinations(db: Session, scope: WarehouseScope, period: Period) -> DestinationsResult:
    """[API-O1] Nơi nhận có lượt xuất trong kỳ: chi nhánh trước đối tác, rồi theo tên."""
    rows = db.execute(
        text(f"""
            SELECT l.counterpart_location_id, loc.name, loc.kind::text, count(*)
            FROM inventory_log l LEFT JOIN locations loc ON loc.id = l.counterpart_location_id
            WHERE {_OUT_ROWS}
            GROUP BY 1, 2, 3
            ORDER BY CASE WHEN loc.kind::text = 'branch' THEN 0 ELSE 1 END, loc.name
        """),
        base_params(scope, period.from_, period.to),
    ).all()
    unknown = next((r[3] for r in rows if r[0] is None), None)
    return DestinationsResult(
        destinations=[
            DestinationOption(id=r[0], name=r[1], kind=r[2], count=r[3]) for r in rows if r[0] is not None
        ],
        unknown_count=unknown,
    )


def out_total(
    db: Session, scope: WarehouseScope, period: Period, ids: list[int] | None, unknown: bool | None
) -> int:
    """[API-O2] Tổng lượt xuất của các nơi nhận đang chọn."""
    params = base_params(scope, period.from_, period.to)
    flt = destination_filter(ids, unknown, params)
    return db.execute(
        text(f"SELECT count(*) FROM inventory_log l WHERE {_OUT_ROWS} {flt}"), params
    ).scalar_one()


def out_by_destination(
    db: Session,
    scope: WarehouseScope,
    period: Period,
    ids: list[int] | None,
    unknown: bool | None,
    limit: int | None,
) -> ByDestinationResult:
    """[API-O3] Bảng (B): mỗi nơi nhận một dòng, sắp số lượt giảm dần; `limit` chỉ cắt danh sách nơi nhận."""
    params = base_params(scope, period.from_, period.to)
    flt = destination_filter(ids, unknown, params)
    rows = db.execute(
        text(f"""
            SELECT l.counterpart_location_id, loc.name, loc.kind::text, count(*),
                   count(DISTINCT l.item_id), max((l.event_time AT TIME ZONE :tz)::date)
            FROM inventory_log l LEFT JOIN locations loc ON loc.id = l.counterpart_location_id
            WHERE {_OUT_ROWS} {flt}
            GROUP BY 1, 2, 3
            ORDER BY count(*) DESC, CASE WHEN loc.kind::text = 'branch' THEN 0 ELSE 1 END, loc.name
        """),
        params,
    ).all()
    named = [
        DestinationRow(id=r[0], name=r[1], kind=r[2], count=r[3], item_count=r[4], last_date=r[5])
        for r in rows
        if r[0] is not None
    ]
    unk = next((UnknownRow(count=r[3], item_count=r[4], last_date=r[5]) for r in rows if r[0] is None), None)
    return ByDestinationResult(destinations=named[:limit] if limit else named, unknown=unk)


def out_daily(
    db: Session, scope: WarehouseScope, period: Period, ids: list[int] | None, unknown: bool | None
) -> DailyResult:
    """[API-O4] Lượt xuất mỗi ngày theo nơi nhận: top 5 nơi + "Khác" + "Chưa rõ"; đủ ngày, ngày trống = 0."""
    params = base_params(scope, period.from_, period.to)
    flt = destination_filter(ids, unknown, params)
    rows = db.execute(
        text(f"""
            SELECT (l.event_time AT TIME ZONE :tz)::date, l.counterpart_location_id,
                   loc.name, loc.kind::text, count(*)
            FROM inventory_log l LEFT JOIN locations loc ON loc.id = l.counterpart_location_id
            WHERE {_OUT_ROWS} {flt}
            GROUP BY 1, 2, 3, 4
        """),
        params,
    ).all()
    totals: dict[int, int] = defaultdict(int)
    info: dict[int, tuple[str, str]] = {}
    has_unknown = False
    for _day, dest_id, name, kind, n in rows:
        if dest_id is None:
            has_unknown = True
        else:
            totals[dest_id] += n
            info[dest_id] = (name, kind)
    # Top theo tổng lượt (đồng hạng: id nhỏ trước) để thứ tự/màu series ổn định
    ranked = sorted(totals, key=lambda d: (-totals[d], d))
    top = ranked[:MAX_SERIES]
    series = [Series(key=str(d), name=info[d][0], kind=info[d][1]) for d in top]
    if len(ranked) > MAX_SERIES:
        series.append(Series(key="other", name="Khác", kind="other"))
    if has_unknown:
        series.append(Series(key="unknown", name=UNKNOWN_NAME, kind="unknown"))

    per_day: dict[date, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for day, dest_id, _name, _kind, n in rows:
        key = "unknown" if dest_id is None else str(dest_id) if dest_id in top else "other"
        per_day[day][key] += n
    days = []
    for offset in range((period.to - period.from_).days + 1):
        d = date.fromordinal(period.from_.toordinal() + offset)
        counts = dict(per_day.get(d, {}))
        days.append(Day(date=d, total=sum(counts.values()), counts=counts))
    return DailyResult(series=series, days=days)


def out_top_items(
    db: Session,
    scope: WarehouseScope,
    period: Period,
    ids: list[int] | None,
    unknown: bool | None,
    limit: int,
) -> list[TopItem]:
    """[API-O5] Top mặt hàng theo SỐ LƯỢT xuất (không so sánh số lượng giữa các đơn vị khác nhau).

    Đồng hạng lượt thì xét `qty_base` (cùng đơn vị gốc của mặt hàng đó), rồi tên.
    """
    params = base_params(scope, period.from_, period.to) | {"limit": limit}
    flt = destination_filter(ids, unknown, params)
    rows = db.execute(
        text(f"""
            SELECT i.id, i.code, i.name, i.base_unit, count(*), sum(-l.delta_base)
            FROM inventory_log l JOIN items i ON i.id = l.item_id
            WHERE {_OUT_ROWS} {flt}
            GROUP BY i.id, i.code, i.name, i.base_unit
            ORDER BY count(*) DESC, sum(-l.delta_base) DESC, i.name, i.id
            LIMIT :limit
        """),
        params,
    ).all()
    return [TopItem(item_id=r[0], code=r[1], name=r[2], unit=r[3], count=r[4], qty_base=r[5]) for r in rows]


def out_transactions(
    db: Session,
    scope: WarehouseScope,
    period: Period,
    ids: list[int] | None,
    unknown: bool | None,
    *,
    q: str | None,
    page: int,
    page_size: int,
) -> OutTransactionPage:
    """[API-O6] Danh sách lượt xuất, mới nhất trước; `q` tìm theo tên hoặc Mã VT."""
    params = base_params(scope, period.from_, period.to) | {
        "limit": page_size,
        "offset": (page - 1) * page_size,
    }
    flt = destination_filter(ids, unknown, params)
    if q and q.strip():
        flt += " AND (i.name ILIKE :q ESCAPE '\\' OR i.code ILIKE :q ESCAPE '\\')"
        params["q"] = f"%{escape_like(q.strip())}%"
    rows, total = fetch_page(
        db,
        text(f"""
            SELECT l.id, i.id, i.code, i.name, l.unit, l.qty, (l.event_time AT TIME ZONE :tz)::date,
                   l.counterpart_location_id, loc.name, loc.kind::text, count(*) OVER() AS total
            FROM inventory_log l
            JOIN items i ON i.id = l.item_id
            LEFT JOIN locations loc ON loc.id = l.counterpart_location_id
            WHERE {_OUT_ROWS} {flt}
            ORDER BY l.event_time DESC, l.id DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
        total_col=10,
    )
    return OutTransactionPage(
        total=total,
        rows=[
            OutTransaction(
                id=r[0],
                item_id=r[1],
                code=r[2],
                name=r[3],
                unit=r[4],
                qty=r[5],
                event_date=r[6],
                destination_id=r[7],
                destination_name=r[8],
                destination_kind=r[9],
            )
            for r in rows
        ],
    )
