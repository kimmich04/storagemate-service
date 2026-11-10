"""Số liệu trang Nhập Kho: lượt nhập (dòng IN) của kho tổng, SQL thuần như stock/service.py."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.inventory.counted_rows import COUNTED_ROWS, FROM_START, UPTO_END, base_params, escape_like
from app.inventory.dependencies import WarehouseScope
from app.inventory.period import Period
from app.paging import fetch_page


@dataclass(frozen=True)
class InDay:
    date: date
    count: int


@dataclass(frozen=True)
class InTransaction:
    id: int
    item_id: int
    code: str | None
    name: str
    unit: str
    qty: Decimal
    event_date: date


@dataclass(frozen=True)
class InTransactionPage:
    total: int
    rows: list[InTransaction]


def in_daily(db: Session, scope: WarehouseScope, period: Period) -> list[InDay]:
    """[API-I1] Số lượt nhập mỗi ngày trong kỳ (generate_series nên ngày trống = 0)."""
    rows = db.execute(
        text(f"""
            WITH days AS (
                SELECT d::date AS day
                FROM generate_series(CAST(:from AS date), CAST(:to AS date), interval '1 day') d
            ), counts AS (
                SELECT (l.event_time AT TIME ZONE :tz)::date AS day, count(*) AS n
                FROM inventory_log l
                WHERE {COUNTED_ROWS} AND l.action = 'IN' AND {FROM_START} AND {UPTO_END}
                GROUP BY 1
            )
            SELECT days.day, coalesce(c.n, 0) FROM days LEFT JOIN counts c USING (day) ORDER BY days.day
        """),
        base_params(scope, period.from_, period.to),
    ).all()
    return [InDay(date=r[0], count=r[1]) for r in rows]


def in_transactions(
    db: Session, scope: WarehouseScope, period: Period, *, q: str | None, page: int, page_size: int
) -> InTransactionPage:
    """[API-I2] Danh sách lượt nhập trong kỳ, mới nhất trước; `q` tìm theo tên hoặc Mã VT."""
    params = base_params(scope, period.from_, period.to) | {
        "limit": page_size,
        "offset": (page - 1) * page_size,
    }
    search = ""
    if q and q.strip():
        search = " AND (i.name ILIKE :q ESCAPE '\\' OR i.code ILIKE :q ESCAPE '\\')"
        params["q"] = f"%{escape_like(q.strip())}%"
    rows, total = fetch_page(
        db,
        text(f"""
            SELECT l.id, i.id, i.code, i.name, l.unit, l.qty,
                   (l.event_time AT TIME ZONE :tz)::date, count(*) OVER() AS total
            FROM inventory_log l JOIN items i ON i.id = l.item_id
            WHERE {COUNTED_ROWS} AND l.action = 'IN' AND {FROM_START} AND {UPTO_END} {search}
            ORDER BY l.event_time DESC, l.id DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
        total_col=7,
    )
    return InTransactionPage(
        total=total,
        rows=[
            InTransaction(id=r[0], item_id=r[1], code=r[2], name=r[3], unit=r[4], qty=r[5], event_date=r[6])
            for r in rows
        ],
    )
