"""⚡ /webhooks/zalo — Zalo gọi, KHÔNG phải UI.

Kiểm secret → lưu mẫu → INSERT inbound_messages (trùng thì bỏ qua) → trả 200 ngay.
Xử lý ở worker (app/worker.py).
"""

import hmac
import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.channels.zalo import parse_update, save_sample
from app.config import settings
from app.database import get_db
from app.messaging import inbox

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

SUCCESS = {"message": "Success"}

DbSession = Annotated[Session, Depends(get_db)]


def get_webhook_secret() -> str:
    return settings.ZALO_WEBHOOK_SECRET


def get_samples_dir() -> Path:
    return Path(settings.ZALO_SAMPLES_DIR)


def verify_zalo_secret(
    secret: Annotated[str, Depends(get_webhook_secret)],
    x_bot_api_secret_token: Annotated[str | None, Header()] = None,
) -> None:
    """Chạy trước khi đọc body. Secret chưa cấu hình → từ chối tất cả."""
    received = (x_bot_api_secret_token or "").encode()
    if not secret or not hmac.compare_digest(received, secret.encode()):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


@router.post("/zalo", dependencies=[Depends(verify_zalo_secret)])
def zalo_webhook(
    payload: Annotated[dict, Body()],
    db: DbSession,
    samples_dir: Annotated[Path, Depends(get_samples_dir)],
) -> dict[str, str]:
    save_sample(payload, samples_dir)
    msg = parse_update(payload)
    if msg is None:
        logger.warning("Bỏ qua payload Zalo không đọc được (event_name=%s)", payload.get("event_name"))
        return SUCCESS
    if not inbox.enqueue(db, msg, payload):
        logger.info("Bỏ qua tin trùng %s", msg.message_id)
    db.commit()
    return SUCCESS
