"""🖥️ /api/dashboard — trang Tổng quan của kho tổng (plan mục 8.5). Mỗi component một endpoint.

Gắn vào router /dashboard ở `dashboard/router.py`. Phạm vi cố định là kho tổng; kỳ theo
`month` + `from` + `to` (plan mục 0). Khối "Xuất theo nơi nhận" dùng lại
GET /api/transactions/out/by-destination?limit=5 [API-O3] nên không có endpoint riêng ở đây.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.dashboard import service as dashboard_service
from app.dashboard.overview import service
from app.dashboard.overview.schemas import (
    DayInOutRead,
    InOutRead,
    InStockRead,
    KpiRead,
    RecentTransactionsRead,
    RecentTxRead,
)
from app.dashboard.schemas import StaffStatRead, StaffStatsRead
from app.database import DbSession
from app.inventory.dependencies import Scope
from app.inventory.period import SelectedPeriod, to_read
from app.inventory.stock.service import in_stock_counts

router = APIRouter()


@router.get("/kpis/stock-in")
def get_stock_in_kpi(db: DbSession, scope: Scope, period: SelectedPeriod) -> KpiRead:
    """[API-T1] Ô "Lượt nhập": số lượt nhập trong kỳ; khớp `total` của Nhập Kho."""
    return service.kpi(db, scope, period, lambda m: m.in_count)


@router.get("/kpis/items-in")
def get_items_in_kpi(db: DbSession, scope: Scope, period: SelectedPeriod) -> KpiRead:
    """[API-T2] Ô "Mặt hàng được nhập": số mặt hàng khác nhau có lượt nhập trong kỳ."""
    return service.kpi(db, scope, period, lambda m: m.items_in)


@router.get("/kpis/stock-out")
def get_stock_out_kpi(db: DbSession, scope: Scope, period: SelectedPeriod) -> KpiRead:
    """[API-T3] Ô "Lượt xuất": số lượt xuất trong kỳ; khớp ô (A) của Xuất Kho khi chọn hết nơi nhận."""
    return service.kpi(db, scope, period, lambda m: m.out_count)


@router.get("/kpis/destinations")
def get_destinations_kpi(db: DbSession, scope: Scope, period: SelectedPeriod) -> KpiRead:
    """[API-T4] Ô "Nơi nhận": số nơi nhận có lượt xuất trong kỳ (không tính "chưa rõ nơi nhận")."""
    return service.kpi(db, scope, period, lambda m: m.destinations)


@router.get("/kpis/in-stock")
def get_in_stock_kpi(db: DbSession, scope: Scope, period: SelectedPeriod) -> InStockRead:
    """[API-T5] Ô "Còn tồn" (đã gộp tồn đầu kỳ → cuối kỳ): số mặt hàng còn tồn trên tổng số mặt hàng có sổ."""
    opening, closing, total = in_stock_counts(db, scope, period)
    return InStockRead(opening=opening, closing=closing, total=total)


@router.get("/in-out")
def get_in_out(db: DbSession, scope: Scope, period: SelectedPeriod) -> InOutRead:
    """[API-T6] Biểu đồ cột lượt nhập / xuất theo ngày; đủ ngày trong kỳ, ngày trống = 0."""
    days = service.daily_in_out(db, scope, period)
    return InOutRead(
        period=to_read(period),
        days=[DayInOutRead(date=d.date, in_count=d.in_count, out_count=d.out_count) for d in days],
    )


@router.get("/staff")
def get_staff_stats(db: DbSession, scope: Scope, period: SelectedPeriod) -> StaffStatsRead:
    """[API-T9] Bảng Nhân viên của kho tổng trong kỳ: số tin, % tin lệnh đọc thẳng bằng regex, số lần hủy."""
    rows = dashboard_service.staff_stats(db, scope, period.from_, period.to)
    return StaffStatsRead(staff=[StaffStatRead.model_validate(r) for r in rows])


@router.get("/recent-transactions")
def get_recent_transactions(
    db: DbSession, scope: Scope, limit: Annotated[int, Query(ge=1, le=50)] = 10
) -> RecentTransactionsRead:
    """[API-T8] Giao dịch gần đây: `limit` lượt nhập/xuất mới nhất của kho tổng, không phụ thuộc bộ lọc kỳ."""
    rows = service.recent_transactions(db, scope, limit)
    return RecentTransactionsRead(items=[RecentTxRead.model_validate(r, from_attributes=True) for r in rows])
