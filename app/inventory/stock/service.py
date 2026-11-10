"""Số liệu trang Tồn Kho đọc thẳng từ inventory_log của kho tổng (SQL thuần, như dashboard/service.py).

Mọi hàm nhận `Period` đã resolve (from/to theo múi giờ tenant) và `WarehouseScope`.
Đơn vị luôn là đơn vị gốc (items.base_unit) vì số lượng lấy từ delta_base.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Row, text
from sqlalchemy.orm import Session

from app.inventory.counted_rows import FROM_START, UPTO_END, escape_like
from app.inventory.dependencies import WarehouseScope
from app.inventory.period import Period
from app.paging import fetch_page


class StatusFilter(StrEnum):
    ALL = "all"
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    VARIANCE = "variance"


class SortKey(StrEnum):
    NAME = "name"
    CODE = "code"
    CATEGORY = "category"
    CLOSING = "closing"
    VARIANCE = "variance"


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


# Khóa sắp xếp -> biểu thức SQL (danh sách trắng, không nhận chuỗi từ người dùng)
_SORT_SQL = {
    SortKey.NAME: "lower(name)",
    SortKey.CODE: "code",
    SortKey.CATEGORY: "category",
    SortKey.CLOSING: "closing",
    SortKey.VARIANCE: "variance",
}

UNKNOWN_KEY = "null"  # khóa của nhóm "Chưa rõ nơi nhận" trong `outbound`

# Dòng được tính: bỏ dòng hủy và dòng đã bị hủy. Cộng delta_base thì cặp này tự triệt tiêu,
# nhưng loại hẳn để cột Nhập/Xuất/... không bị lệch khi dòng gốc và dòng hủy rơi vào hai kỳ khác nhau.
_LIVE_ROWS = """
    l.tenant_id = :tenant AND l.location_id = :loc
    AND l.reverses_id IS NULL
    AND NOT EXISTS (SELECT 1 FROM inventory_log r WHERE r.reverses_id = l.id)
"""


@dataclass(frozen=True)
class StockKpis:
    total_items: int
    in_stock: int
    variance: int


@dataclass(frozen=True)
class Destination:
    id: int | None
    name: str
    kind: str


@dataclass(frozen=True)
class StockRow:
    item_id: int
    code: str | None
    name: str
    category: str | None
    unit: str
    opening: Decimal
    inbound: Decimal
    outbound: dict[str, Decimal]
    outbound_total: Decimal
    waste: Decimal
    variance: Decimal
    other: Decimal
    closing: Decimal


@dataclass(frozen=True)
class StockPage:
    total: int
    rows: list[StockRow]


def _params(scope: WarehouseScope, period: Period) -> dict[str, object]:
    return {
        "tenant": scope.tenant_id,
        "loc": scope.location.id,
        "tz": scope.timezone,
        "from": period.from_,
        "to": period.to,
    }


def _item_filters(category: list[str] | None, q: str | None, params: dict[str, object]) -> str:
    """Điều kiện lọc nhóm hàng và tìm tên/Mã VT; thêm tham số bind vào `params`."""
    sql = ""
    if category:
        sql += " AND i.category = ANY(CAST(:categories AS text[]))"
        params["categories"] = category
    if q and q.strip():
        sql += " AND (i.name ILIKE :q ESCAPE '\\' OR i.code ILIKE :q ESCAPE '\\')"
        params["q"] = f"%{escape_like(q.strip())}%"
    return sql


def _breakdown_cte(item_filters: str) -> str:
    """CTE `filtered`: mỗi mặt hàng có sổ ở kho tổng đến hết `to`, kèm các cột đã cộng.

    opening = mọi dòng trước `from` + dòng nạp tồn đầu (`opening`) dù rơi trong kỳ, để kỳ chứa ngày nạp
    (09/2026) hiện đúng "Tồn đầu" thay vì dồn vào cột Khác; closing = mọi dòng đến hết `to`;
    mặt hàng đã archive không hiện (khớp Tổng quan và Nhóm hàng);
    variance = ADJUST không phải tồn đầu kỳ (âm = thiếu hàng so với sổ).
    """
    return f"""
        WITH live AS (
            SELECT l.item_id, l.action, l.delta_base, l.parser_source,
                   (l.event_time AT TIME ZONE :tz)::date AS d
            FROM inventory_log l
            WHERE {_LIVE_ROWS} AND {UPTO_END}
        ), agg AS (
            SELECT item_id,
                   coalesce(sum(delta_base) FILTER (
                       WHERE d < :from OR parser_source = 'opening'), 0) AS opening,
                   coalesce(sum(delta_base) FILTER (WHERE d >= :from AND action = 'IN'), 0) AS inbound,
                   coalesce(sum(-delta_base) FILTER (
                       WHERE d >= :from AND action = 'OUT'), 0) AS outbound_total,
                   coalesce(sum(-delta_base) FILTER (WHERE d >= :from AND action = 'WASTE'), 0) AS waste,
                   coalesce(sum(delta_base) FILTER (
                       WHERE d >= :from AND action = 'ADJUST' AND parser_source <> 'opening'), 0) AS variance,
                   sum(delta_base) AS closing,
                   count(*) FILTER (WHERE d >= :from AND parser_source <> 'opening') AS moved
            FROM live
            GROUP BY item_id
        ), filtered AS (
            SELECT i.id AS item_id, i.code, i.name, i.category, i.base_unit AS unit,
                   a.opening, a.inbound, a.outbound_total, a.waste, a.variance, a.closing, a.moved
            FROM agg a JOIN items i ON i.id = a.item_id
            WHERE i.tenant_id = :tenant AND i.archived_at IS NULL {item_filters}
        )
    """


def stock_kpis(
    db: Session, scope: WarehouseScope, period: Period, category: list[str] | None, q: str | None
) -> StockKpis:
    """[API-S1] [API-S2] [API-S3] Ba thẻ KPI.

    Không nhận `status` để số trên thẻ không đổi khi bấm thẻ lọc bảng.
    """
    params = _params(scope, period)
    cte = _breakdown_cte(_item_filters(category, q, params))
    row = db.execute(
        text(f"""
            {cte}
            SELECT count(*),
                   count(*) FILTER (WHERE closing > 0),
                   count(*) FILTER (WHERE variance <> 0)
            FROM filtered
        """),
        params,
    ).one()
    return StockKpis(total_items=row[0], in_stock=row[1], variance=row[2])


def stock_destinations(db: Session, scope: WarehouseScope, period: Period) -> list[Destination]:
    """[API-S4] Mọi nơi nhận có lượt xuất trong kỳ: chi nhánh, đối tác, rồi "Chưa rõ nơi nhận" (nếu có)."""
    rows = db.execute(
        text(f"""
            SELECT l.counterpart_location_id, loc.name, loc.kind::text
            FROM inventory_log l
            LEFT JOIN locations loc ON loc.id = l.counterpart_location_id
            WHERE {_LIVE_ROWS} AND l.action = 'OUT' AND {FROM_START} AND {UPTO_END}
            GROUP BY 1, 2, 3
            ORDER BY CASE WHEN l.counterpart_location_id IS NULL THEN 2
                          WHEN loc.kind::text = 'partner' THEN 1 ELSE 0 END,
                     loc.name
        """),
        _params(scope, period),
    ).all()
    return [
        Destination(id=r[0], name=r[1], kind=r[2])
        if r[0] is not None
        else Destination(None, "Chưa rõ nơi nhận", "unknown")
        for r in rows
    ]


def _outbound_by_item(
    db: Session, scope: WarehouseScope, period: Period, item_ids: list[int]
) -> dict[int, dict[str, Decimal]]:
    """Xuất trong kỳ của các mặt hàng trong trang, theo nơi nhận."""
    if not item_ids:
        return {}
    params = _params(scope, period) | {"ids": item_ids}
    rows = db.execute(
        text(f"""
            SELECT l.item_id, l.counterpart_location_id, sum(-l.delta_base)
            FROM inventory_log l
            WHERE {_LIVE_ROWS} AND l.action = 'OUT' AND {FROM_START} AND {UPTO_END}
              AND l.item_id = ANY(CAST(:ids AS bigint[]))
            GROUP BY 1, 2
        """),
        params,
    ).all()
    result: dict[int, dict[str, Decimal]] = {}
    for item_id, dest_id, qty in rows:
        result.setdefault(item_id, {})[UNKNOWN_KEY if dest_id is None else str(dest_id)] = qty
    return result


def _status_sql(status: StatusFilter, only_moved: bool) -> str:
    conds = []
    if status is StatusFilter.IN_STOCK:
        conds.append("closing > 0")
    elif status is StatusFilter.OUT_OF_STOCK:
        conds.append("closing <= 0")
    elif status is StatusFilter.VARIANCE:
        conds.append("variance <> 0")
    if only_moved:
        conds.append("moved > 0")
    return f"WHERE {' AND '.join(conds)}" if conds else ""


def _stock_row(r: Row, outbound: dict[str, Decimal]) -> StockRow:
    """Một dòng của câu truy vấn bảng chính -> StockRow; thứ tự cột xem SELECT trong `stock_table`."""
    opening, inbound, outbound_total, waste, variance, closing = r[5], r[6], r[7], r[8], r[9], r[10]
    return StockRow(
        item_id=r[0],
        code=r[1],
        name=r[2],
        category=r[3],
        unit=r[4],
        opening=opening,
        inbound=inbound,
        outbound=outbound,
        outbound_total=outbound_total,
        waste=waste,
        variance=variance,
        # phần dư để luôn có closing = opening + inbound − outbound − waste + variance + other
        other=closing - opening - inbound + outbound_total + waste - variance,
        closing=closing,
    )


def stock_table(
    db: Session,
    scope: WarehouseScope,
    period: Period,
    *,
    category: list[str] | None,
    q: str | None,
    status: StatusFilter,
    only_moved: bool,
    sort: SortKey,
    order: SortOrder,
    page: int,
    page_size: int,
) -> StockPage:
    """[API-S5] Bảng chính: một dòng / mặt hàng, đã lọc, sắp xếp, phân trang."""
    params = _params(scope, period) | {"limit": page_size, "offset": (page - 1) * page_size}
    cte = _breakdown_cte(_item_filters(category, q, params))
    direction = "DESC" if order is SortOrder.DESC else "ASC"
    rows, total = fetch_page(
        db,
        text(f"""
            {cte}
            SELECT item_id, code, name, category, unit, opening, inbound, outbound_total, waste,
                   variance, closing, count(*) OVER() AS total
            FROM filtered
            {_status_sql(status, only_moved)}
            ORDER BY {_SORT_SQL[sort]} {direction} NULLS LAST, item_id
            LIMIT :limit OFFSET :offset
        """),
        params,
        total_col=11,
    )
    outbound = _outbound_by_item(db, scope, period, [r[0] for r in rows])
    return StockPage(
        total=total,
        rows=[_stock_row(r, outbound.get(r[0], {})) for r in rows],
    )
