"""🖥️ /api/reports — UI xem báo cáo."""

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user

router = APIRouter(
    prefix="/reports",
    tags=["reports"],
    dependencies=[Depends(get_current_user)],
)

# TODO — endpoint theo plan:
#   GET /api/reports/daily
#   GET /api/reports/monthly
