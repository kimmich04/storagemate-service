"""🖥️ /api/stock và /api/transactions — UI xem tồn và lịch sử."""

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user

stock_router = APIRouter(
    prefix="/stock",
    tags=["stock"],
    dependencies=[Depends(get_current_user)],
)

# TODO — endpoint theo plan:
#   GET /api/stock   tồn hiện tại (view current_stock)


transactions_router = APIRouter(
    prefix="/transactions",
    tags=["transactions"],
    dependencies=[Depends(get_current_user)],
)

# TODO — endpoint theo plan:
#   GET  /api/transactions                lịch sử nhập/xuất, lọc theo nguyên liệu, nhân viên, ngày
#   POST /api/transactions/{id}/reverse   tạo bản ghi bù trừ
