"""🖥️ /api/staff — UI quản lý nhân viên."""

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user

router = APIRouter(
    prefix="/staff",
    tags=["staff"],
    dependencies=[Depends(get_current_user)],
)

# TODO — endpoint theo plan:
#   GET   /api/staff               danh sách nhân viên
#   POST  /api/staff               thêm nhân viên
#   PATCH /api/staff/{id}          đổi vai trò, khóa/mở
#   POST  /api/staff/{id}/invite   sinh mã mời + deeplink/QR của bot
