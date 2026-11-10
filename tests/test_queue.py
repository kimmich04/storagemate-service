"""Worker process_next(): claim → nhân viên → dispatcher → ghi sổ → commit → gửi trả lời (DB thật)."""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels.base import InboundMessage
from app.config import settings
from app.inventory.models import InventoryLog, PendingAction
from app.messaging import inbox
from app.messaging.dispatcher import Outcome
from app.messaging.models import InboundMessage as InboundRow
from app.messaging.pending import PendingStore
from app.messaging.queue import process_next
from app.parser.regex import Phieu, RawLine
from tests.fakes import FakeLlm, FakeSender

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 11, 5, 15, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
FREE_TEXT = "hôm qua nhập 10 hộp cà phê kem béo về kho tổng"
LLM_PHIEU = Phieu(
    action="IN",
    date=NOW.date(),
    date_note=None,
    from_loc="?",
    to_loc="kho tổng",
    lines=[RawLine(raw="Cà phê kem béo: 10", name="Cà phê kem béo", qty=Decimal(10), unit=None, note=None)],
    bad_lines=[],
    warnings=[],
)
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


async def _run(
    session_factory, db: Session, text: str, message_id: str, llm: FakeLlm, minutes: int = 0
) -> FakeSender:
    _enqueue(db, text, message_id=message_id)
    sender = FakeSender()
    await process_next(session_factory, sender, PendingStore(), now=NOW + timedelta(minutes=minutes), llm=llm)
    db.expire_all()
    return sender


def _ledger(db: Session) -> list[InventoryLog]:
    return list(db.scalars(select(InventoryLog)))


def _pending(db: Session) -> list[PendingAction]:
    return list(db.scalars(select(PendingAction).order_by(PendingAction.id)))


async def test_free_text_asks_for_ok_and_writes_nothing_before_ok(
    session_factory: Callable[[], Session], db_session: Session, seeded: SimpleNamespace
) -> None:
    llm = FakeLlm(LLM_PHIEU)

    sender = await _run(session_factory, db_session, FREE_TEXT, "f1", llm)

    assert llm.calls == [FREE_TEXT]
    assert _ledger(db_session) == []
    [waiting] = _pending(db_session)
    assert (waiting.status, waiting.parser_source, waiting.inbound_id) == (
        "waiting",
        "llm",
        _row(db_session, "f1").id,
    )
    assert _row(db_session, "f1").route == "llm_waiting"
    assert "Gõ OK để ghi sổ" in "\n".join(sender.messages())


async def test_ok_writes_ledger_with_source_llm_and_closes_pending(
    session_factory: Callable[[], Session], db_session: Session, seeded: SimpleNamespace
) -> None:
    llm = FakeLlm(LLM_PHIEU)
    await _run(session_factory, db_session, FREE_TEXT, "f1", llm)

    sender = await _run(session_factory, db_session, "OK", "f2", llm, minutes=1)

    [entry] = _ledger(db_session)
    assert (entry.parser_source, entry.action, entry.qty, entry.inbound_id) == (
        "llm", "IN", Decimal(10), _row(db_session, "f1").id,
    )  # fmt: skip
    assert entry.raw_message == FREE_TEXT
    assert [p.status for p in _pending(db_session)] == ["confirmed"]
    assert (_row(db_session, "f1").route, _row(db_session, "f2").route) == ("phieu", "phieu_answer")
    assert "✅ Đã ghi 1/1 dòng" in "\n".join(sender.messages())
    assert llm.calls == [FREE_TEXT]  # "OK" không tốn thêm một lần gọi LLM


async def test_second_ok_does_not_write_again(
    session_factory: Callable[[], Session], db_session: Session, seeded: SimpleNamespace
) -> None:
    llm = FakeLlm(LLM_PHIEU)
    await _run(session_factory, db_session, FREE_TEXT, "f1", llm)
    await _run(session_factory, db_session, "OK", "f2", llm, minutes=1)

    sender = await _run(session_factory, db_session, "ok", "f3", llm, minutes=2)

    assert len(_ledger(db_session)) == 1
    assert "không có phiếu nào đang chờ" in "\n".join(sender.messages())


async def test_sai_discards_pending_without_writing(
    session_factory: Callable[[], Session], db_session: Session, seeded: SimpleNamespace
) -> None:
    llm = FakeLlm(LLM_PHIEU)
    await _run(session_factory, db_session, FREE_TEXT, "f1", llm)

    sender = await _run(session_factory, db_session, "Sai", "f2", llm, minutes=1)

    assert _ledger(db_session) == []
    assert [p.status for p in _pending(db_session)] == ["rejected"]
    assert _row(db_session, "f2").route == "llm_rejected"
    assert "Đã hủy" in "\n".join(sender.messages())


async def test_ok_after_ttl_expires_pending_without_writing(
    session_factory: Callable[[], Session], db_session: Session, seeded: SimpleNamespace
) -> None:
    llm = FakeLlm(LLM_PHIEU)
    await _run(session_factory, db_session, FREE_TEXT, "f1", llm)

    sender = await _run(
        session_factory, db_session, "OK", "f2", llm, minutes=settings.PENDING_TTL_MINUTES + 1
    )

    assert _ledger(db_session) == []
    assert [p.status for p in _pending(db_session)] == ["expired"]
    assert "hết hạn" in "\n".join(sender.messages())


async def test_other_message_ends_pending_and_is_handled_normally(
    session_factory: Callable[[], Session], db_session: Session, seeded: SimpleNamespace
) -> None:
    llm = FakeLlm(LLM_PHIEU)
    await _run(session_factory, db_session, FREE_TEXT, "f1", llm)

    sender = await _run(session_factory, db_session, "menu", "f2", llm, minutes=1)

    assert [p.status for p in _pending(db_session)] == ["expired"]
    assert "bot ghi phiếu" in "\n".join(sender.messages())
    assert _ledger(db_session) == []


@pytest.mark.parametrize("llm", [FakeLlm(None), None], ids=["llm_did_not_understand", "llm_disabled"])
async def test_free_text_gets_unknown_reply_when_llm_cannot_read_it(
    session_factory: Callable[[], Session], db_session: Session, seeded: SimpleNamespace, llm: FakeLlm | None
) -> None:
    _enqueue(db_session, "hello bạn ơi", message_id="f1")
    sender = FakeSender()

    await process_next(session_factory, sender, PendingStore(), now=NOW, llm=llm)

    db_session.expire_all()
    assert (_row(db_session, "f1").status, _row(db_session, "f1").route) == ("done", "other")
    assert "chưa hiểu" in "\n".join(sender.messages())
    assert _pending(db_session) == []


async def test_phieu_regex_can_read_never_calls_llm(
    session_factory: Callable[[], Session], db_session: Session, seeded: SimpleNamespace
) -> None:
    llm = FakeLlm(LLM_PHIEU)

    await _run(session_factory, db_session, PHIEU, "f1", llm)

    assert llm.calls == []
    assert [e.parser_source for e in _ledger(db_session)] == ["regex"]
