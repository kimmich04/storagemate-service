"""🖥️ Gom router của domain inventory cho api.py: /api/period, /api/stock, /api/transactions.

Code từng trang nằm ở subfolder: stock/ (Tồn Kho), transactions/inbound, transactions/outbound (sau này).
"""

from fastapi import APIRouter

from app.database import DbSession
from app.inventory import period as period_service
from app.inventory.dependencies import Scope
from app.inventory.period import PeriodOptionsRead, SelectedPeriod
from app.inventory.stock.router import router as stock_router  # noqa: F401  (re-export cho api.py: /api/stock)

period_router = APIRouter(prefix="/period", tags=["period"])


@period_router.get("")
def get_period(db: DbSession, scope: Scope, period: SelectedPeriod) -> PeriodOptionsRead:
    """[API-P0] Bộ lọc kỳ dùng chung 5 trang: tháng dương + khoảng ngày (plan mục 0).

    Trả danh sách tháng chọn được (`months`), kỳ đã chuẩn hóa (`from`, `to`) và biên chọn ngày
    (`minDate`, `maxDate`). Vi phạm ràng buộc → 422 `{code: "invalid_period", message}`.
    """
    return period_service.period_options(db, scope, period)


# /api/transactions (Nhập Kho; Xuất Kho sau này) — code ở transactions/
from app.inventory.transactions.router import router as transactions_router  # noqa: E402,F401
