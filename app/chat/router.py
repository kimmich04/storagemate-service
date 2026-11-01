"""🖥️ /api/chat — UI web chat demo."""

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user

router = APIRouter(
    prefix="/chat",
    tags=["chat"],
    dependencies=[Depends(get_current_user)],
)

# TODO — endpoint theo plan:
#   POST /api/chat/messages   gửi tin vào pipeline (qua channels/web.py)
#   GET  /api/chat/messages   đọc câu trả lời
