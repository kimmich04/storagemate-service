"""🖥️ /api/labels — UI duyệt nhãn."""

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user

router = APIRouter(
    prefix="/labels",
    tags=["labels"],
    dependencies=[Depends(get_current_user)],
)

# TODO — endpoint theo plan:
#   GET   /api/labels        danh sách mẫu chờ duyệt
#   PATCH /api/labels/{id}   sửa/duyệt nhãn
