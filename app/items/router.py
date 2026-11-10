"""🖥️ /api/items — UI quản lý danh mục. Giai đoạn này chỉ có các API ĐỌC cho trang Danh mục hàng hóa."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.auth.dependencies import CurrentAdmin
from app.database import DbSession
from app.items import service
from app.items.schemas import (
    CategoryRead,
    ItemLocationsRead,
    ItemRead,
    ItemsPageRead,
    LocationOptionRead,
    UnitRead,
)
from app.paging import PageQuery

# Không gắn get_current_user ở cấp router vì hàm này chưa hiện thực (luôn 501);
# mỗi route tự dùng CurrentAdmin.
router = APIRouter(prefix="/items", tags=["items"])

# TODO — endpoint ghi, CHỜ người dùng cho phép (plan 4d.3/4d.5):
#   GET /api/items/{id}, GET /api/items/next-code, GET /api/items/check-duplicate
#   POST /api/items, PATCH /api/items/{id}, POST /api/items/{id}/archive|restore, DELETE /api/items/{id}

LocationIds = Annotated[
    list[int] | None,
    Query(alias="locationId", description="Lọc theo kho; lặp được. Bỏ trống = mọi mặt hàng"),
]
NoTransactions = Annotated[
    bool | None,
    Query(alias="noTransactions", description="true = gồm các mặt hàng chưa có dòng sổ nào ở bất kỳ kho nào"),
]


@router.get("/categories")
def get_categories(
    db: DbSession,
    admin: CurrentAdmin,
    location_id: LocationIds = None,
    no_transactions: NoTransactions = None,
) -> list[CategoryRead]:
    """[API-C0] Dropdown "Nhóm hàng" (dùng chung Tồn Kho và Danh mục): [{name, count}]."""
    return [
        CategoryRead(name=n, count=c)
        for n, c in service.list_categories(db, admin.tenant_id, location_id, no_transactions)
    ]


@router.get("/locations")
def get_locations(db: DbSession, admin: CurrentAdmin) -> ItemLocationsRead:
    """[API-D1] Dropdown "Kho": kho tổng và chi nhánh kèm số mặt hàng, và số mặt hàng chưa có giao dịch."""
    result = service.list_locations(db, admin.tenant_id)
    return ItemLocationsRead(
        locations=[
            LocationOptionRead(id=loc.id, name=loc.name, kind=loc.kind, item_count=loc.item_count)
            for loc in result.locations
        ],
        no_transactions_count=result.no_transactions_count,
    )


@router.get("")
def get_items(
    db: DbSession,
    admin: CurrentAdmin,
    location_id: LocationIds = None,
    no_transactions: NoTransactions = None,
    category: Annotated[list[str] | None, Query(description="Lọc nhóm hàng; lặp được")] = None,
    q: Annotated[
        str | None, Query(description="Tìm theo tên, Mã VT hoặc tên gọi khác; không phân biệt hoa thường")
    ] = None,
    page: PageQuery = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=200)] = 50,
) -> ItemsPageRead:
    """[API-D2] Ô tìm + bảng danh mục hàng hóa (chỉ mặt hàng chưa lưu trữ, sắp theo tên)."""
    result = service.list_items(
        db,
        admin.tenant_id,
        location_ids=location_id,
        no_transactions=no_transactions,
        category=category,
        q=q,
        page=page,
        page_size=page_size,
    )
    return ItemsPageRead(
        total=result.total,
        page=page,
        page_size=page_size,
        items=[
            ItemRead(
                id=i.id,
                code=i.code,
                name=i.name,
                category=i.category,
                unit=i.unit,
                min_qty=i.min_qty,
                units=[UnitRead(name=u.name, factor=u.factor) for u in i.units],
                matched_alias=i.matched_alias,
            )
            for i in result.rows
        ],
    )
