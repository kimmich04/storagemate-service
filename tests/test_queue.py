"""Worker process_next(): claim → nhân viên → dispatcher → ghi sổ → commit → gửi trả lời (DB thật)."""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels.base import InboundMessage
from app.inventory.models import InventoryLog
from app.messaging import inbox
from app.messaging.dispatcher import Outcome
from app.messaging.models import InboundMessage as InboundRow
from app.messaging.pending import PendingStore
from app.messaging.queue import process_next
from tests.fakes import FakeSender

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 11, 5, 15, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
PHIEU = "ngày 05/11 nhập hàng về kho tổng\nCà phê kem béo: 10\nxyz abc khong co: 3"


def _enqueue(db: Session, text: str, chat_id: str = "chat-1", message_id: str = "m1") -> None:
    msg = InboundMessage(
        "zalo", message_id, chat_id, "user-1", "NV", "text", text, None, NOW - timedelta(minutes=1)
    )
    inbox.enqueue(db, msg, {})
    db.commit()


def _row(db: Session, message_id: str = "m1") -> InboundRow:
    return db.scalars(select(InboundRow).where(InboundRow.external_id == message_id)).one()


async def test_empty_queue_returns_false(session_factory: Callable[[], Session]) -> None:
    assert await process_next(session_factory, FakeSender(), PendingStore(), now=NOW) is False


async def test_unlinked_chat_marked_ignored_and_gets_reply(
    session_factory: Callable[[], Session], db_session: Session, seeded: SimpleNamespace
) -> None:
    _enqueue(db_session, "menu", chat_id="stranger")
    sender = FakeSender()

    await process_next(session_factory, sender, PendingStore(), now=NOW)

    db_session.expire_all()
    assert (_row(db_session).status, _row(db_session).route) == ("ignored", "unlinked")
    assert "chưa được liên kết" in sender.messages()[0]


async def test_partial_phieu_route_and_reply_lists_skipped_lines(
    session_factory: Callable[[], Session], db_session: Session, seeded: SimpleNamespace
) -> None:
    _enqueue(db_session, PHIEU)
    sender = FakeSender()

    await process_next(session_factory, sender, PendingStore(), now=NOW)

    db_session.expire_all()
    row = _row(db_session)
    assert (row.status, row.route, row.staff_id) == ("done", "phieu_partial", seeded.staff.id)
    logged = list(db_session.scalars(select(InventoryLog)))
    assert [(r.inbound_id, r.raw_message) for r in logged] == [(row.id, PHIEU)]
    text = "\n".join(sender.messages())
    assert "✅ Đã ghi 1/2 dòng" in text
    assert "«xyz abc khong co: 3» — không tìm thấy món" in text
    assert sender.calls[0] == ("action", "chat-1", "typing")


async def test_handler_error_marks_failed_and_sends_bot_error(
    session_factory: Callable[[], Session],
    db_session: Session,
    seeded: SimpleNamespace,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _enqueue(db_session, PHIEU)
    sender = FakeSender()

    def crash(msg: InboundMessage, now: datetime, pending: PendingStore) -> Outcome:
        raise RuntimeError("boom")

    with caplog.at_level(logging.ERROR):
        await process_next(session_factory, sender, PendingStore(), now=NOW, handle=crash)

    db_session.expire_all()
    row = _row(db_session)
    assert (row.status, row.attempts) == ("failed", 1)
    assert "boom" in row.error and "boom" in caplog.text
    assert sender.messages() == ["⚠️ Bot gặp lỗi, bạn gửi lại giúp mình nhé"]


async def test_reply_sent_only_after_commit(
    session_factory: Callable[[], Session], db_session: Session, seeded: SimpleNamespace
) -> None:
    _enqueue(db_session, PHIEU)
    seen_status: list[str] = []

    class CheckingSender(FakeSender):
        async def send_message(self, chat_id: str, text: str, parse_mode: str | None = None) -> dict:
            with session_factory() as check:
                seen_status.append(_row(check).status)
            return await super().send_message(chat_id, text, parse_mode)

    await process_next(session_factory, CheckingSender(), PendingStore(), now=NOW)

    assert seen_status and set(seen_status) == {"done"}


async def test_phieu_finalised_by_answer_points_to_original_message(
    session_factory: Callable[[], Session], db_session: Session, seeded: SimpleNamespace
) -> None:
    pending = PendingStore()
    _enqueue(
        db_session, "ngày 05/11 nhập hàng về kho tổng\nCà phê kem béo: 2\nCà phê kem béo: 2", message_id="p1"
    )
    await process_next(session_factory, FakeSender(), pending, now=NOW)
    _enqueue(db_session, "a", message_id="p2")

    await process_next(session_factory, FakeSender(), pending, now=NOW + timedelta(minutes=1))

    db_session.expire_all()
    original, answer = _row(db_session, "p1"), _row(db_session, "p2")
    assert (original.route, answer.route) == ("phieu", "phieu_answer")
    logged = list(db_session.scalars(select(InventoryLog)))
    assert [(r.inbound_id, r.qty) for r in logged] == [(original.id, 4)]
