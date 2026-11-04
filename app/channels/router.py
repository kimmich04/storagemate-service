"""⚡ /webhooks/zalo — Zalo gọi, KHÔNG phải UI.

Pha 0 (chưa DB, ngoại lệ đã duyệt): kiểm secret → lưu mẫu → BackgroundTasks chạy process() → trả 200 ngay.
Pha DB: dòng add_task đổi thành enqueue, process() chuyển sang worker.
"""

import hmac
import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Header, HTTPException, Request, status

from app.channels.zalo import parse_update, save_sample
from app.config import settings
from app.messaging.queue import Sender, process

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

SUCCESS = {"message": "Success"}


def get_webhook_secret() -> str:
    return settings.ZALO_WEBHOOK_SECRET


def get_zalo_sender(request: Request) -> Sender:
    return request.app.state.zalo


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
    background: BackgroundTasks,
    sender: Annotated[Sender, Depends(get_zalo_sender)],
    samples_dir: Annotated[Path, Depends(get_samples_dir)],
) -> dict[str, str]:
    save_sample(payload, samples_dir)
    msg = parse_update(payload)
    if msg is None:
        logger.warning("Bỏ qua payload Zalo không đọc được (event_name=%s)", payload.get("event_name"))
        return SUCCESS
    background.add_task(process, msg, sender)
    return SUCCESS
