"""🖥️ /api/items — UI quản lý danh mục."""

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user

router = APIRouter(
    prefix="/items",
    tags=["items"],
    dependencies=[Depends(get_current_user)],
)

# TODO — endpoint theo plan:
#   GET   /api/items         danh sách nguyên liệu
#   POST  /api/items         thêm nguyên liệu
#   PATCH /api/items/{id}    sửa tên gọi khác, đơn vị quy đổi, mức tồn tối thiểu
