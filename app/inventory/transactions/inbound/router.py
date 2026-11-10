"""🖥️ Nhập Kho: /api/transactions/in/daily (I1). Danh sách I2 nằm ở transactions/router.py (dùng chung)."""

from fastapi import APIRouter

from app.database import DbSession
from app.inventory.dependencies import Scope
from app.inventory.period import SelectedPeriod, to_read
from app.inventory.transactions.inbound import service
from app.inventory.transactions.inbound.schemas import InDailyRead, InDayRead

router = APIRouter()


@router.get("/in/daily")
def get_in_daily(db: DbSession, scope: Scope, period: SelectedPeriod) -> InDailyRead:
    """[API-I1] Biểu đồ "Số lượt nhập theo ngày"."""
    days = service.in_daily(db, scope, period)
    return InDailyRead(period=to_read(period), days=[InDayRead(date=d.date, count=d.count) for d in days])
