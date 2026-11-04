import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.channels.base import InboundMessage, Reply
from app.messaging.pending import PendingStore
from app.messaging.queue import SeenCache, process
from tests.fakes import FakeSender

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 11, 3, 9, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))


def _msg(text: str, message_id: str = "m1") -> InboundMessage:
    return InboundMessage("zalo", message_id, "chat-1", "user-1", "NV", "text", text, None, NOW)


async def test_process_shows_typing_then_sends_rendered_replies() -> None:
    sender = FakeSender()

    await process(_msg("menu"), sender, seen=SeenCache(), pending=PendingStore())

    assert sender.calls[0] == ("action", "chat-1", "typing")
    kind, chat_id, text, parse_mode = sender.calls[1]
    assert (kind, chat_id, parse_mode) == ("message", "chat-1", "markdown")
    assert "📋 Chọn nhanh (gõ số):" in text


async def test_same_message_id_is_answered_once() -> None:
    sender, seen, pending = FakeSender(), SeenCache(), PendingStore()

    await process(_msg("menu"), sender, seen=seen, pending=pending)
    calls_after_first = len(sender.calls)
    await process(_msg("menu"), sender, seen=seen, pending=pending)

    assert len(sender.calls) == calls_after_first


async def test_handler_crash_sends_one_error_reply_and_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    sender = FakeSender()

    def crash(msg: InboundMessage, now: datetime, pending: PendingStore) -> list[Reply]:
        raise RuntimeError("boom")

    with caplog.at_level(logging.ERROR):
        await process(_msg("menu"), sender, seen=SeenCache(), pending=PendingStore(), handle=crash)

    assert sender.messages() == ["⚠️ Bot gặp lỗi, bạn gửi lại giúp mình nhé"]
    assert "boom" in caplog.text
