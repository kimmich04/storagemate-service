"""Hàng đợi inbound_messages: chống trùng bằng ON CONFLICT, claim bằng FOR UPDATE SKIP LOCKED."""

from collections.abc import Iterator
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from app.channels.base import InboundMessage
from app.messaging import inbox
from app.messaging.models import InboundMessage as InboundRow

NOW = datetime(2026, 11, 5, 9, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))


def _msg(message_id: str = "m1") -> InboundMessage:
    return InboundMessage("zalo", message_id, "chat-1", "user-1", "NV", "text", "menu", None, NOW)


def test_enqueue_same_message_twice_inserts_one_row(db_session: Session) -> None:
    assert inbox.enqueue(db_session, _msg(), {"raw": 1}) is True
    assert inbox.enqueue(db_session, _msg(), {"raw": 1}) is False

    assert db_session.scalar(select(func.count()).select_from(InboundRow)) == 1


def test_to_message_round_trips_normalised_columns(db_session: Session) -> None:
    inbox.enqueue(db_session, _msg(), {})

    row = inbox.claim_next(db_session, NOW)

    assert row is not None and row.status == "processing" and row.attempts == 1
    assert inbox.to_message(row) == _msg()


@pytest.fixture
def committed(db_engine: Engine) -> Iterator[Engine]:
    """Test khoá giữa 2 kết nối cần dữ liệu đã COMMIT thật — dọn bảng sau test."""
    yield db_engine
    with db_engine.begin() as connection:
        connection.execute(text("TRUNCATE inbound_messages RESTART IDENTITY CASCADE"))


def test_claim_skips_row_locked_by_other_session(committed: Engine) -> None:
    with Session(committed) as setup, setup.begin():
        inbox.enqueue(setup, _msg("m1"), {})
        inbox.enqueue(setup, _msg("m2"), {})

    with Session(committed) as first, Session(committed) as second:
        first.begin()
        second.begin()
        claimed_first = inbox.claim_next(first, NOW)
        claimed_second = inbox.claim_next(second, NOW)
        third = Session(committed)
        third.begin()
        assert inbox.claim_next(third, NOW) is None
        third.rollback()
        third.close()

        assert {claimed_first.external_id, claimed_second.external_id} == {"m1", "m2"}
        first.rollback()
        second.rollback()
