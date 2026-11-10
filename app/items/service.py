"""Danh mục mặt hàng: dựng tên lưu DB từ catalog (`db_names`) và các truy vấn đọc cho trang Danh mục.

Phần đọc dùng SQL thuần như dashboard/service.py. CRUD / tìm theo alias cho parser: spec sau.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.inventory.counted_rows import escape_like
from app.paging import fetch_page
from app.parser.catalog import CatalogItem

_NO_LEDGER = "NOT EXISTS (SELECT 1 FROM inventory_log l WHERE l.item_id = i.id AND l.tenant_id = :tenant)"
_IN_LOCATIONS = """EXISTS (SELECT 1 FROM inventory_log l WHERE l.item_id = i.id AND l.tenant_id = :tenant
                      AND l.location_id = ANY(CAST(:locs AS bigint[])))"""


def location_filter(
    location_ids: list[int] | None, no_transactions: bool | None, params: dict[str, object]
) -> str:
    """Điều kiện SQL lọc theo kho (bắt đầu bằng " AND ", rỗng nếu lấy tất cả mặt hàng); alias bảng `i`.

    Mặt hàng "thuộc kho" khi có dòng sổ ở ít nhất một kho trong `location_ids` (hợp các kho, đếm một lần).
    `no_transactions=True` thêm các mặt hàng chưa có dòng sổ nào ở bất kỳ kho nào.
    Không chọn gì (ids rỗng và no_transactions không phải True) → mọi mặt hàng.
    """
    conds = []
    if location_ids:
        conds.append(_IN_LOCATIONS)
        params["locs"] = location_ids
    if no_transactions:
        conds.append(_NO_LEDGER)
    return f" AND ({' OR '.join(conds)})" if conds else ""


def list_categories(
    db: Session, tenant_id: int, location_ids: list[int] | None, no_transactions: bool | None = None
) -> list[tuple[str, int]]:
    """[API-C0] Nhóm hàng + số mặt hàng (chưa lưu trữ), sắp theo tên nhóm.

    Bộ lọc kho giống `location_filter`, để số đếm khớp với bảng danh mục cùng bộ lọc.
    """
    params: dict[str, object] = {"tenant": tenant_id}
    in_location = location_filter(location_ids, no_transactions, params)
    rows = db.execute(
        text(f"""
            SELECT i.category, count(*)
            FROM items i
            WHERE i.tenant_id = :tenant AND i.archived_at IS NULL AND i.category IS NOT NULL
            {in_location}
            GROUP BY i.category
            ORDER BY i.category
        """),
        params,
    ).all()
    return [(r[0], r[1]) for r in rows]


@dataclass(frozen=True)
class LocationOption:
    id: int
    name: str
    kind: str
    item_count: int


@dataclass(frozen=True)
class LocationsResult:
    locations: list[LocationOption]
    no_transactions_count: int


@dataclass(frozen=True)
class ItemUnit:
    name: str
    factor: Decimal


@dataclass(frozen=True)
class Item:
    id: int
    code: str | None
    name: str
    category: str | None
    unit: str
    min_qty: Decimal
    units: list[ItemUnit]
    matched_alias: str | None


@dataclass(frozen=True)
class ItemPage:
    total: int
    rows: list[Item]


def list_locations(db: Session, tenant_id: int) -> LocationsResult:
    """[API-D1] Kho tổng rồi chi nhánh (không có đối tác), kèm số mặt hàng có sổ ở từng kho."""
    rows = db.execute(
        text("""
            SELECT loc.id, loc.name, loc.kind::text, count(DISTINCT i.id)
            FROM locations loc
            LEFT JOIN inventory_log g ON g.location_id = loc.id AND g.tenant_id = :tenant
            LEFT JOIN items i ON i.id = g.item_id AND i.archived_at IS NULL
            WHERE loc.tenant_id = :tenant AND loc.archived_at IS NULL
              AND loc.kind::text IN ('warehouse', 'branch')
            GROUP BY loc.id, loc.name, loc.kind
            ORDER BY CASE WHEN loc.kind::text = 'warehouse' THEN 0 ELSE 1 END, loc.name
        """),
        {"tenant": tenant_id},
    ).all()
    no_tx = db.execute(
        text(f"""
            SELECT count(*) FROM items i
            WHERE i.tenant_id = :tenant AND i.archived_at IS NULL AND {_NO_LEDGER}
        """),
        {"tenant": tenant_id},
    ).scalar_one()
    return LocationsResult(
        locations=[LocationOption(id=r[0], name=r[1], kind=r[2], item_count=r[3]) for r in rows],
        no_transactions_count=no_tx,
    )


def list_items(
    db: Session,
    tenant_id: int,
    *,
    location_ids: list[int] | None,
    no_transactions: bool | None,
    category: list[str] | None,
    q: str | None,
    page: int,
    page_size: int,
) -> ItemPage:
    """[API-D2] Bảng danh mục: mặt hàng chưa lưu trữ, sắp theo tên (không phân biệt hoa thường).

    `q` tìm theo tên, Mã VT hoặc tên gọi khác; `matched_alias` chỉ có khi khớp qua tên gọi khác mà không khớp
    tên/Mã VT. `units` là các quy đổi đóng gói đã bỏ dòng của chính đơn vị gốc.
    """
    params: dict[str, object] = {"tenant": tenant_id, "limit": page_size, "offset": (page - 1) * page_size}
    where = location_filter(location_ids, no_transactions, params)
    if category:
        where += " AND i.category = ANY(CAST(:categories AS text[]))"
        params["categories"] = category
    alias_col = "NULL"
    if q and q.strip():
        params["q"] = f"%{escape_like(q.strip())}%"
        alias_match = "a.item_id = i.id AND a.alias ILIKE :q ESCAPE '\\'"
        by_name = "i.name ILIKE :q ESCAPE '\\' OR i.code ILIKE :q ESCAPE '\\'"
        where += f" AND ({by_name} OR EXISTS (SELECT 1 FROM item_aliases a WHERE {alias_match}))"
        alias_col = f"""CASE WHEN {by_name} THEN NULL ELSE
            (SELECT a.alias FROM item_aliases a WHERE {alias_match} ORDER BY length(a.alias), a.alias LIMIT 1)
            END"""
    rows, total = fetch_page(
        db,
        text(f"""
            SELECT i.id, i.code, i.name, i.category, i.base_unit, i.min_qty,
                   coalesce((SELECT json_agg(json_build_object('name', u.unit_name, 'factor', u.factor)
                                             ORDER BY u.factor, u.unit_name)
                             FROM units u WHERE u.item_id = i.id AND u.unit_name <> i.base_unit), '[]'::json),
                   {alias_col},
                   count(*) OVER() AS total
            FROM items i
            WHERE i.tenant_id = :tenant AND i.archived_at IS NULL {where}
            ORDER BY lower(i.name), i.id
            LIMIT :limit OFFSET :offset
        """),
        params,
        total_col=8,
    )
    return ItemPage(
        total=total,
        rows=[
            Item(
                id=r[0],
                code=r[1],
                name=r[2],
                category=r[3],
                unit=r[4],
                min_qty=r[5],
                units=[ItemUnit(name=u["name"], factor=Decimal(str(u["factor"]))) for u in r[6]],
                matched_alias=r[7],
            )
            for r in rows
        ],
    )


def db_names(catalog: Iterable[CatalogItem]) -> dict[str, str]:
    """code → tên lưu bảng items. DB bắt UNIQUE(tenant, lower(name)); catalog có tên trùng khác ĐVT
    (vd «Bột kem trứng» Gói/Túi) → món sau thêm «(ĐVT)», món sau nữa thêm cả mã."""
    names: dict[str, str] = {}
    used: set[str] = set()
    for item in catalog:
        name = item.name
        for candidate in (item.name, f"{item.name} ({item.base_unit})", f"{item.name} ({item.code})"):
            if candidate.lower() not in used:
                name = candidate
                break
        used.add(name.lower())
        names[item.code] = name
    return names
