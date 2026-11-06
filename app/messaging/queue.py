"""Worker xử lý một tin: claim → nhận diện nhân viên → dispatcher → ghi sổ → COMMIT → gửi trả lời.

Mỗi tin một transaction. Tin trả lời chỉ gửi sau COMMIT; gửi lỗi thì chỉ log (sổ đã đúng, gửi lại dễ ghi đôi).
"""

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session

from app.channels.base import InboundMessage, Reply
from app.channels.zalo import LOCAL_TZ, render
from app.inventory import ledger
from app.messaging import dispatcher, inbox, replies
from app.messaging.dispatcher import ROUTE_ANSWER, Outcome
from app.messaging.models import InboundMessage as InboundRow
from app.messaging.pending import PendingStore
from app.staff import service as staff_service
from app.staff.models import Location, Staff

logger = logging.getLogger(__name__)

ROUTE_UNLINKED = "unlinked"
ROUTE_INVITE_OK, ROUTE_INVITE_FAILED = "invite_ok", "invite_failed"  # Phase 4 đếm invite_failed để khoá

Handler = Callable[[InboundMessage, datetime, PendingStore], Outcome]
SessionFactory = Callable[[], Session]


class Sender(Protocol):
    async def send_chat_action(self, chat_id: str, action: str = "typing") -> dict: ...

    async def send_message(self, chat_id: str, text: str, parse_mode: str | None = None) -> dict: ...


async def process_next(
    session_factory: SessionFactory,
    sender: Sender,
    pending: PendingStore,
    *,
    now: datetime | None = None,
    handle: Handler = dispatcher.handle,
) -> bool:
    """False khi hàng đợi rỗng. Lỗi xử lý tin không raise: tin → failed, nhân viên nhận câu báo lỗi."""
    now = now or datetime.now(LOCAL_TZ)
    with session_factory() as session:
        session.begin()
        row = inbox.claim_next(session, now)
        if row is None:
            session.rollback()
            return False
        row_id, chat_id = row.id, row.chat_id
        try:
            await sender.send_chat_action(chat_id, "typing")
            answer = _handle_row(session, row, now, pending, handle)
            session.commit()
        except Exception as error:
            logger.exception("Xử lý tin %s thất bại", row_id)
            session.rollback()
            with session.begin():
                inbox.mark_failed(session, row_id, repr(error), now)
            answer = [replies.bot_error()]
    await _send(sender, chat_id, answer)
    return True


def _handle_row(
    session: Session, row: InboundRow, now: datetime, pending: PendingStore, handle: Handler
) -> list[Reply]:
    staff = staff_service.find_by_chat_id(session, row.chat_id)
    if staff is None:
        return _handle_unlinked(session, row, now)
    row.staff_id, row.tenant_id = staff.id, staff.tenant_id
    outcome = handle(inbox.to_message(row), now, pending)
    answer = list(outcome.replies)
    route = outcome.route
    if outcome.phieu is not None and outcome.origin is not None:
        route = _record(session, row, outcome, staff, now, answer)
    inbox.finish(row, "done", now, route)
    return answer


def _handle_unlinked(session: Session, row: InboundRow, now: datetime) -> list[Reply]:
    """Chat chưa gắn nhân viên chỉ được gửi mã mời; không đi vào dispatcher nên không ghi được sổ."""
    code = staff_service.normalize_code(row.text)
    if code is None:
        inbox.finish(row, "ignored", now, ROUTE_UNLINKED)
        return [replies.invite_needed()]
    staff = staff_service.redeem_invite(session, code, row.chat_id, row.sender_id, now)
    if staff is None:
        logger.info("Chat %s nhập mã mời không hợp lệ", row.chat_id)
        inbox.finish(row, "done", now, ROUTE_INVITE_FAILED)
        return [replies.invite_rejected()]
    logger.info("Chat %s đã gắn với nhân viên %s", row.chat_id, staff.id)
    row.staff_id, row.tenant_id = staff.id, staff.tenant_id
    inbox.finish(row, "done", now, ROUTE_INVITE_OK)
    location = session.get(Location, staff.default_location_id)
    return replies.welcome(staff.name, location.name)


def _record(
    session: Session, row: InboundRow, outcome: Outcome, staff: Staff, now: datetime, answer: list[Reply]
) -> str:
    """Ghi phiếu đã chốt; trả route cho tin hiện tại. Phiếu chốt bằng A/C thì route nằm trên tin gốc."""
    origin_row = row
    if outcome.origin.message_id != row.external_id:
        origin_row = inbox.find(session, row.channel, outcome.origin.message_id) or row
    result = ledger.record(
        session,
        outcome.phieu,
        staff=staff,
        inbound_id=origin_row.id,
        raw_message=origin_row.text,
        sent_at=outcome.origin.sent_at,
        now=now,
    )
    if reply := replies.ledger_result(outcome.phieu, result):
        answer.append(reply)
    if origin_row is row:
        return result.route
    origin_row.route = result.route
    return ROUTE_ANSWER


async def _send(sender: Sender, chat_id: str, answer: list[Reply]) -> None:
    try:
        for reply in answer:
            for chunk in render(reply):
                await sender.send_message(chat_id, chunk, parse_mode=reply.parse_mode)
    except Exception:
        logger.exception("Không gửi được trả lời tới chat %s", chat_id)
