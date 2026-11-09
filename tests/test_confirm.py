"""Bản chờ OK/Sai: (de)serialize Phieu, tạo bản chờ, mỗi chat một bản 'waiting' (DB thật cho phần sau)."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels.base import InboundMessage
from app.config import settings
from app.inventory import confirm
from app.inventory.models import PendingAction
from app.messaging import inbox
from app.parser.regex import Phieu, RawLine

NOW = datetime(2026, 11, 5, 15, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
PHIEU = Phieu(
    action="OUT",
    date=date(2026, 11, 4),
    date_note="tự lấy ngày / giờ nhận tin",
    from_loc="kho tổng",
    to_loc="kho 220",
    lines=[RawLine(raw="Đường: 0.5 kg", name="Đường", qty=Decimal("0.5"), unit="kg", note="gấp")],
    bad_lines=["???"],
    warnings=["w"],
)


def _inbound_id(db: Session, message_id: str = "m1") -> int:
    msg = InboundMessage("zalo", message_id, "chat-1", "u", "NV", "text", "x", None, NOW)
    inbox.enqueue(db, msg, {})
    return inbox.find(db, "zalo", message_id).id


def _create(db: Session, seeded: SimpleNamespace, message_id: str, now: datetime) -> PendingAction:
    return confirm.create(
        db,
        staff=seeded.staff,
        chat_id="chat-1",
        inbound_id=_inbound_id(db, message_id),
        phieu=PHIEU,
        source="llm",
        now=now,
    )


def test_phieu_survives_json_round_trip_with_exact_decimal() -> None:
    assert confirm.phieu_from_json(confirm.phieu_to_json(PHIEU)) == PHIEU


def test_create_stores_waiting_row_that_expires_after_ttl(
    db_session: Session, seeded: SimpleNamespace
) -> None:
    row = _create(db_session, seeded, "m1", NOW)

    assert (row.status, row.parser_source, row.tenant_id) == ("waiting", "llm", seeded.tenant.id)
    assert row.expires_at == NOW + timedelta(minutes=settings.PENDING_TTL_MINUTES)
    assert confirm.phieu_from_json(row.parsed) == PHIEU
    assert confirm.find_waiting(db_session, "chat-1").id == row.id


def test_new_pending_expires_the_old_one_for_same_chat(db_session: Session, seeded: SimpleNamespace) -> None:
    first = _create(db_session, seeded, "m1", NOW)
    second = _create(db_session, seeded, "m2", NOW + timedelta(minutes=1))

    db_session.expire_all()
    statuses = {r.id: r.status for r in db_session.scalars(select(PendingAction))}
    assert statuses == {first.id: "expired", second.id: "waiting"}


def test_resolve_closes_the_pending(db_session: Session, seeded: SimpleNamespace) -> None:
    row = _create(db_session, seeded, "m1", NOW)

    confirm.resolve(row, "confirmed", NOW)
    db_session.flush()

    assert confirm.find_waiting(db_session, "chat-1") is None
    assert (row.status, row.resolved_at) == ("confirmed", NOW)
