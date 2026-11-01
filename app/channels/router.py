"""⚡ /webhooks/zalo — Zalo gọi, KHÔNG phải UI."""

from fastapi import APIRouter

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# TODO Pha 0:
#   POST /webhooks/zalo   kiểm tra header X-Bot-Api-Secret-Token,
#                         lưu inbound_messages (chống trùng), trả 200 ngay
