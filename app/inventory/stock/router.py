"""🖥️ /api/stock — trang Tồn Kho. Mỗi component một endpoint (plan mục 8.1).

Phạm vi cố định là kho tổng (không có location_id).
Tham số kỳ: `month` (YYYY-MM) + `from` + `to` (plan mục 0).
Đăng nhập: dùng CurrentAdmin qua dependency `Scope`, giống /api/dashboard.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.database import DbSession
from app.inventory.dependencies import Scope
from app.inventory.period import SelectedPeriod, to_read
from app.inventory.stock import service
from app.inventory.stock.schemas import CountRead, DestinationRead, StockItemRead, StockRead
from app.inventory.stock.service import SortKey, SortOrder, StatusFilter
from app.paging import PageQuery

router = APIRouter(prefix="/stock", tags=["stock"])

CategoryQuery = Annotated[
    list[str] | None, Query(description="Lọc nhóm hàng; lặp được (?category=A&category=B)")
]
SearchQuery = Annotated[str | None, Query(description="Tìm theo tên hoặc Mã VT, không phân biệt hoa thường")]


@router.get("/kpis/total-items")
def get_total_items(
    db: DbSession, scope: Scope, period: SelectedPeriod, category: CategoryQuery = None, q: SearchQuery = None
) -> CountRead:
    """[API-S1] Thẻ "Tổng số mặt hàng": mặt hàng có sổ ở kho tổng đến hết `to`."""
    return CountRead(count=service.stock_kpis(db, scope, period, category, q).total_items)


@router.get("/kpis/in-stock")
def get_in_stock(
    db: DbSession, scope: Scope, period: SelectedPeriod, category: CategoryQuery = None, q: SearchQuery = None
) -> CountRead:
    """[API-S2] Thẻ "Mặt hàng còn tồn": tồn cuối kỳ > 0."""
    return CountRead(count=service.stock_kpis(db, scope, period, category, q).in_stock)


@router.get("/kpis/variance")
def get_variance(
    db: DbSession, scope: Scope, period: SelectedPeriod, category: CategoryQuery = None, q: SearchQuery = None
) -> CountRead:
    """[API-S3] Thẻ "Mặt hàng có chênh lệch": 0 cho tới khi có dòng kiểm kê (ADJUST không phải tồn đầu)."""
    return CountRead(count=service.stock_kpis(db, scope, period, category, q).variance)


@router.get("/destinations")
def get_destinations(db: DbSession, scope: Scope, period: SelectedPeriod) -> list[DestinationRead]:
    """[API-S4] Các cột nơi nhận của nhóm cột Xuất: nơi có lượt xuất trong kỳ."""
    return [DestinationRead.model_validate(d) for d in service.stock_destinations(db, scope, period)]


@router.get("")
def get_stock(
    db: DbSession,
    scope: Scope,
    period: SelectedPeriod,
    category: CategoryQuery = None,
    q: SearchQuery = None,
    status: StatusFilter = StatusFilter.ALL,
    only_moved: Annotated[
        bool, Query(alias="onlyMoved", description="Chỉ mặt hàng có biến động trong kỳ")
    ] = False,
    sort: SortKey = SortKey.NAME,
    order: SortOrder = SortOrder.ASC,
    page: PageQuery = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=200)] = 50,
) -> StockRead:
    """[API-S5] Bảng chính: opening, inbound, outbound theo nơi nhận, waste, variance, other, closing."""
    result = service.stock_table(
        db,
        scope,
        period,
        category=category,
        q=q,
        status=status,
        only_moved=only_moved,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )
    return StockRead(
        period=to_read(period),
        total=result.total,
        page=page,
        page_size=page_size,
        items=[StockItemRead.model_validate(r) for r in result.rows],
    )
