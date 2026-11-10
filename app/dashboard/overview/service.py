"""Số liệu trang Tổng quan của kho tổng (SQL thuần như inbound/outbound). Chỉ đọc.

Đếm "lượt" dùng chung `COUNTED_ROWS` với Nhập Kho / Xuất Kho nên các ô KPI luôn khớp số của trang con.
`deltaPct` so với CÙNG DÃY SỐ NGÀY của tháng liền trước (plan mục 0 điều 7).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.dashboard.overview.schemas import KpiRead
from app.inventory.counted_rows import (
    BALANCING_NOTE_PREFIX,
    COUNTED_ROWS,
    FROM_START,
    UPTO_END,
    base_params,
)
from app.inventory.dependencies import WarehouseScope
from app.inventory.period import Period

_IN_OUT_ROWS = f"{COUNTED_ROWS} AND l.action IN ('IN', 'OUT') AND {FROM_START} AND {UPTO_END}"


@dataclass(frozen=True)
class PeriodMetrics:
    in_count: int  # lượt nhập
    items_in: int  # số mặt hàng khác nhau được nhập
    out_count: int  # lượt xuất
    destinations: int  # số nơi nhận có lượt xuất (không tính "chưa rõ nơi nhận")


@dataclass(frozen=True)
class DayInOut:
    date: date
    in_count: int
    out_count: int


@dataclass(frozen=True)
class RecentTx:
    id: int
    kind: str  # "in" | "out"
    name: str
    unit: str
    qty: Decimal
    event_date: date
    destination_name: str | None


def previous_month_range(period: Period) -> tuple[date, date]:
    """Cùng dãy số ngày của tháng liền trước; ngày vượt độ dài tháng trước thì cắt ở ngày cuối tháng đó.

    Ví dụ 1/11–9/11 → 1/10–9/10; 29/3–31/3 → 28/2–28/2 (năm thường).
    """
    last_of_previous = period.min_date - timedelta(days=1)

    def clip(day: date) -> date:
        return last_of_previous.replace(day=min(day.day, last_of_previous.day))

    return clip(period.from_), clip(period.to)


def delta_pct(current: int, previous: int) -> int | None:
    """% thay đổi so với kỳ trước; kỳ trước = 0 thì không so sánh được → None."""
    return None if previous == 0 else round((current - previous) / previous * 100)


def period_metrics(db: Session, scope: WarehouseScope, from_: date, to: date) -> PeriodMetrics:
    """Bốn con số của [API-T1..T4] trong một câu truy vấn."""
    row = db.execute(
        text(f"""
            SELECT count(*) FILTER (WHERE l.action = 'IN'),
                   count(DISTINCT l.item_id) FILTER (WHERE l.action = 'IN'),
                   count(*) FILTER (WHERE l.action = 'OUT'),
                   count(DISTINCT l.counterpart_location_id) FILTER (WHERE l.action = 'OUT')
            FROM inventory_log l
            WHERE {_IN_OUT_ROWS}
        """),
        base_params(scope, from_, to),
    ).one()
    return PeriodMetrics(in_count=row[0], items_in=row[1], out_count=row[2], destinations=row[3])


def kpi(db: Session, scope: WarehouseScope, period: Period, pick: Callable[[PeriodMetrics], int]) -> KpiRead:
    """[API-T1] [API-T2] [API-T3] [API-T4] Giá trị `pick` của kỳ chọn + % so với tháng liền trước."""
    current = pick(period_metrics(db, scope, period.from_, period.to))
    previous = pick(period_metrics(db, scope, *previous_month_range(period)))
    return KpiRead(value=current, delta_pct=delta_pct(current, previous))


def daily_in_out(db: Session, scope: WarehouseScope, period: Period) -> list[DayInOut]:
    """[API-T6] Lượt nhập / xuất mỗi ngày; đủ mọi ngày từ `from` đến `to`, ngày trống = 0."""
    rows = db.execute(
        text(f"""
            WITH days AS (
                SELECT d::date AS day
                FROM generate_series(CAST(:from AS date), CAST(:to AS date), interval '1 day') d
            ), counts AS (
                SELECT (l.event_time AT TIME ZONE :tz)::date AS day,
                       count(*) FILTER (WHERE l.action = 'IN')  AS in_count,
                       count(*) FILTER (WHERE l.action = 'OUT') AS out_count
                FROM inventory_log l
                WHERE {_IN_OUT_ROWS}
                GROUP BY 1
            )
            SELECT days.day, coalesce(c.in_count, 0), coalesce(c.out_count, 0)
            FROM days LEFT JOIN counts c USING (day)
            ORDER BY days.day
        """),
        base_params(scope, period.from_, period.to),
    ).all()
    return [DayInOut(date=r[0], in_count=r[1], out_count=r[2]) for r in rows]


def recent_transactions(db: Session, scope: WarehouseScope, limit: int) -> list[RecentTx]:
    """[API-T8] `limit` lượt nhập/xuất mới nhất của kho tổng, trộn hai loại; không phụ thuộc bộ lọc kỳ."""
    # :from/:to không dùng ở đây nên không đi qua base_params
    params = {
        "tenant": scope.tenant_id,
        "loc": scope.location.id,
        "tz": scope.timezone,
        "balancing": f"{BALANCING_NOTE_PREFIX}%",
        "limit": limit,
    }
    rows = db.execute(
        text(f"""
            SELECT l.id, l.action::text, i.name, l.unit, l.qty,
                   (l.event_time AT TIME ZONE :tz)::date, cp.name
            FROM inventory_log l
            JOIN items i ON i.id = l.item_id
            LEFT JOIN locations cp ON cp.id = l.counterpart_location_id
            WHERE {COUNTED_ROWS} AND l.action IN ('IN', 'OUT')
            ORDER BY l.event_time DESC, l.id DESC
            LIMIT :limit
        """),
        params,
    ).all()
    return [
        RecentTx(
            id=r[0],
            kind=r[1].lower(),
            name=r[2],
            unit=r[3],
            qty=r[4],
            event_date=r[5],
            destination_name=r[6] if r[1] == "OUT" else None,
        )
        for r in rows
    ]
