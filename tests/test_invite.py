"""Mã mời: chat chưa gắn gửi mã → gắn vào nhân viên; mọi mã không hợp lệ bị từ chối cùng một câu (DB thật)."""

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
from app.messaging.models import InboundMessage as InboundRow
from app.messaging.pending import PendingStore
from app.messaging.queue import process_next
from app.staff import service as staff_service
from app.staff.models import InviteCode, Staff
from tests.fakes import FakeSender

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 11, 6, 15, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
REJECTED = "❌ Mã mời không đúng hoặc đã hết hạn"


def _new_staff(db: Session, seeded: SimpleNamespace, name: str = "Hoa", active: bool = True) -> Staff:
    staff = Staff(
        tenant_id=seeded.tenant.id, default_location_id=seeded.locations["KT"].id, name=name, active=active
    )
    db.add(staff)
    db.flush()
    return staff


async def _send(
    factory: Callable[[], Session],
    db: Session,
    text: str | None,
    chat_id: str = "chat-new",
    msg_id: str = "m1",
) -> tuple[InboundRow, list[str]]:
    event = "text" if text is not None else "sticker"
    msg = InboundMessage("zalo", msg_id, chat_id, f"user-{chat_id}", "NV mới", event, text, None, NOW)
    inbox.enqueue(db, msg, {})
    db.commit()
    sender = FakeSender()
    await process_next(factory, sender, PendingStore(), now=NOW)
    db.expire_all()
    row = db.scalars(select(InboundRow).where(InboundRow.external_id == msg_id)).one()
    return row, sender.messages()


async def test_valid_code_links_chat_and_marks_code_used(
    session_factory: Callable[[], Session], db_session: Session, seeded: SimpleNamespace
) -> None:
    staff = _new_staff(db_session, seeded)
    invite = staff_service.create_invite(db_session, staff, NOW - timedelta(hours=1))

    row, texts = await _send(session_factory, db_session, invite.code)

    assert (row.status, row.route, row.staff_id) == ("done", "invite_ok", staff.id)
    assert (staff.zalo_chat_id, staff.zalo_user_id, staff.linked_at) == ("chat-new", "user-chat-new", NOW)
    assert db_session.get(InviteCode, invite.id).used_at == NOW
    assert texts[0].startswith("Chào Hoa 👋 Bạn đã được kết nối với Kho tổng SG")
    assert "Tên hàng: số lượng" in texts[1]


async def test_code_is_case_and_space_insensitive(
    session_factory: Callable[[], Session], db_session: Session, seeded: SimpleNamespace
) -> None:
    staff = _new_staff(db_session, seeded)
    code = staff_service.create_invite(db_session, staff, NOW).code

    row, _ = await _send(session_factory, db_session, f" {code[:3].lower()} {code[3:].lower()} ")

    assert row.route == "invite_ok"


@pytest.mark.parametrize("problem", ["unknown", "expired", "used", "revoked", "inactive_staff"])
async def test_invalid_codes_rejected_with_same_reply(
    session_factory: Callable[[], Session], db_session: Session, seeded: SimpleNamespace, problem: str
) -> None:
    staff = _new_staff(db_session, seeded, active=problem != "inactive_staff")
    invite = staff_service.create_invite(db_session, staff, NOW)
    if problem == "expired":
        invite.expires_at = NOW - timedelta(minutes=1)
    if problem == "used":
        invite.used_at = NOW - timedelta(hours=1)
    if problem == "revoked":
        invite.revoked_at = NOW - timedelta(hours=1)
    db_session.flush()
    code = "ZZZZZ9" if problem == "unknown" and invite.code != "ZZZZZ9" else invite.code

    row, texts = await _send(session_factory, db_session, code)

    assert (row.status, row.route) == ("done", "invite_failed")
    assert texts == [texts[0]] and texts[0].startswith(REJECTED)
    assert staff.zalo_chat_id is None


async def test_unlinked_non_code_text_asks_for_code(
    session_factory: Callable[[], Session], db_session: Session, seeded: SimpleNamespace
) -> None:
    row, texts = await _send(
        session_factory, db_session, "ngày 06/11 nhập hàng về kho tổng\nCà phê kem béo: 5"
    )

    assert (row.status, row.route) == ("ignored", "unlinked")
    assert "Gửi mã mời 6 ký tự" in texts[0]
    assert db_session.scalars(select(InventoryLog)).first() is None


async def test_unlinked_sticker_asks_for_code(
    session_factory: Callable[[], Session], db_session: Session, seeded: SimpleNamespace
) -> None:
    row, texts = await _send(session_factory, db_session, None)

    assert row.route == "unlinked" and "Gửi mã mời" in texts[0]


async def test_linked_chat_sending_code_is_normal_text(
    session_factory: Callable[[], Session], db_session: Session, seeded: SimpleNamespace
) -> None:
    staff = _new_staff(db_session, seeded)
    code = staff_service.create_invite(db_session, staff, NOW).code

    row, _ = await _send(session_factory, db_session, code, chat_id="chat-1")  # chat-1 = Lan, đã gắn

    assert row.route == "other"
    assert staff.zalo_chat_id is None


async def test_new_code_relinks_staff_to_new_chat(
    session_factory: Callable[[], Session], db_session: Session, seeded: SimpleNamespace
) -> None:
    staff = _new_staff(db_session, seeded)
    first = staff_service.create_invite(db_session, staff, NOW)
    await _send(session_factory, db_session, first.code, chat_id="old-phone", msg_id="m1")
    second = staff_service.create_invite(db_session, staff, NOW)

    row, _ = await _send(session_factory, db_session, second.code, chat_id="new-phone", msg_id="m2")

    assert row.route == "invite_ok"
    assert staff.zalo_chat_id == "new-phone"


async def test_chat_held_by_inactive_staff_moves_to_new_staff(
    session_factory: Callable[[], Session], db_session: Session, seeded: SimpleNamespace
) -> None:
    former = _new_staff(db_session, seeded, name="Cũ", active=False)
    former.zalo_chat_id, former.zalo_user_id = "chat-new", "user-chat-new"
    rehired = _new_staff(db_session, seeded, name="Mới")
    code = staff_service.create_invite(db_session, rehired, NOW).code

    row, _ = await _send(session_factory, db_session, code)

    assert row.route == "invite_ok"
    assert (former.zalo_chat_id, former.zalo_user_id) == (None, None)
    assert rehired.zalo_chat_id == "chat-new"


async def test_zalo_user_of_active_staff_rejected(
    session_factory: Callable[[], Session], db_session: Session, seeded: SimpleNamespace
) -> None:
    holder = _new_staff(db_session, seeded, name="Đang làm")
    holder.zalo_user_id = "user-chat-new"
    staff = _new_staff(db_session, seeded)
    code = staff_service.create_invite(db_session, staff, NOW).code

    row, texts = await _send(session_factory, db_session, code)

    assert row.route == "invite_failed" and texts[0].startswith(REJECTED)
    assert staff.zalo_chat_id is None


def test_create_invite_revokes_previous_unused_code(db_session: Session, seeded: SimpleNamespace) -> None:
    staff = _new_staff(db_session, seeded)
    first = staff_service.create_invite(db_session, staff, NOW)

    second = staff_service.create_invite(db_session, staff, NOW + timedelta(minutes=5))

    assert first.revoked_at == NOW + timedelta(minutes=5)
    assert second.revoked_at is None and second.expires_at == NOW + timedelta(minutes=5, hours=24)
    assert staff_service.CODE_RE.fullmatch(second.code)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("k7p2q9", "K7P2Q9"),
        (" K7P 2Q9 ", "K7P2Q9"),
        ("K7P2Q", None),
        ("K7P2Q9X", None),
        ("menu", None),
        (None, None),
    ],
)
def test_normalize_code(text: str | None, expected: str | None) -> None:
    assert staff_service.normalize_code(text) == expected
