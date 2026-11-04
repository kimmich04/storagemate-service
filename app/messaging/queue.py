"""Xử lý một tin nhắn từ đầu đến cuối: chống trùng → dispatcher → gửi trả lời.

Pha 0 (chưa DB): webhook chạy process() qua BackgroundTasks, polling gọi thẳng. Pha DB: webhook enqueue,
worker lấy tin ra rồi gọi đúng hàm này.
"""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Protocol

from app.channels.base import InboundMessage, Reply
from app.channels.zalo import LOCAL_TZ, render
from app.messaging import dispatcher, replies
from app.messaging.pending import PendingStore

logger = logging.getLogger(__name__)

SEEN_TTL = timedelta(hours=1)

Handler = Callable[[InboundMessage, datetime, PendingStore], list[Reply]]


class Sender(Protocol):
    async def send_chat_action(self, chat_id: str, action: str = "typing") -> dict: ...

    async def send_message(self, chat_id: str, text: str, parse_mode: str | None = None) -> dict: ...


class SeenCache:
    """message_id đã xử lý trong 1 giờ qua — Zalo có thể gửi lại cùng một tin."""

    # ponytail: dict trong RAM, quét hết mỗi lần thêm; Pha DB thay bằng ON CONFLICT (channel, message_id).
    def __init__(self) -> None:
        self._expires_at: dict[str, datetime] = {}

    def add_if_new(self, key: str, now: datetime) -> bool:
        self._expires_at = {k: expiry for k, expiry in self._expires_at.items() if expiry > now}
        if key in self._expires_at:
            return False
        self._expires_at[key] = now + SEEN_TTL
        return True


SEEN = SeenCache()
PENDING = PendingStore()


async def process(
    msg: InboundMessage,
    sender: Sender,
    *,
    seen: SeenCache = SEEN,
    pending: PendingStore = PENDING,
    handle: Handler = dispatcher.handle,
) -> None:
    """Không bao giờ raise: lỗi được log và nhân viên nhận một câu báo lỗi ngắn."""
    now = datetime.now(LOCAL_TZ)
    if not seen.add_if_new(f"{msg.channel}:{msg.message_id}", now):
        logger.info("Bỏ qua tin trùng %s", msg.message_id)
        return
    try:
        await sender.send_chat_action(msg.chat_id, "typing")
        for reply in handle(msg, now, pending):
            for chunk in render(reply):
                await sender.send_message(msg.chat_id, chunk, parse_mode=reply.parse_mode)
    except Exception:
        logger.exception("Xử lý tin %s thất bại", msg.message_id)
        await _send_error(sender, msg.chat_id)


async def _send_error(sender: Sender, chat_id: str) -> None:
    error = replies.bot_error()
    try:
        await sender.send_message(chat_id, error.text, parse_mode=error.parse_mode)
    except Exception:
        logger.exception("Không gửi được tin báo lỗi tới chat %s", chat_id)
