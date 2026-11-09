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
from app.inventory import confirm, ledger
from app.inventory.models import PendingAction
from app.messaging import dispatcher, inbox, replies
from app.messaging.dispatcher import CONFIRM_WORDS, ROUTE_ANSWER, WORD_NO, Outcome
from app.messaging.models import InboundMessage as InboundRow
from app.messaging.pending import PendingStore
from app.parser.catalog import resolve
from app.parser.llm import LlmParser
from app.parser.normalize import fold
from app.staff import service as staff_service
from app.staff.models import Location, Staff

logger = logging.getLogger(__name__)

ROUTE_UNLINKED = "unlinked"
ROUTE_LLM_WAITING, ROUTE_LLM_REJECTED, ROUTE_LLM_EXPIRED = "llm_waiting", "llm_rejected", "llm_expired"
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
    llm: LlmParser | None = None,
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
            answer = await _handle_row(session, row, now, pending, handle, llm)
            session.commit()
        except Exception as error:
            logger.exception("Xử lý tin %s thất bại", row_id)
            session.rollback()
            with session.begin():
                inbox.mark_failed(session, row_id, repr(error), now)
            answer = [replies.bot_error()]
    await _send(sender, chat_id, answer)
    return True


async def _handle_row(
    session: Session,
    row: InboundRow,
    now: datetime,
    pending: PendingStore,
    handle: Handler,
    llm: LlmParser | None,
) -> list[Reply]:
    staff = staff_service.find_by_chat_id(session, row.chat_id)
    if staff is None:
        return _handle_unlinked(session, row, now)
    row.staff_id, row.tenant_id = staff.id, staff.tenant_id
    if (answered := _answer_pending(session, row, staff, now)) is not None:
        return answered
    outcome = handle(inbox.to_message(row), now, pending)
    answer = list(outcome.replies)
    route = outcome.route
    held = await _ask_llm(session, row, staff, now, llm) if outcome.wants_llm else None
    if held is not None:
        answer, route = held, ROUTE_LLM_WAITING
    elif outcome.phieu is not None and outcome.origin is not None:
        route = _record(session, row, outcome, staff, now, answer)
    inbox.finish(row, "done", now, route)
    return answer


def _answer_pending(session: Session, row: InboundRow, staff: Staff, now: datetime) -> list[Reply] | None:
    """Chat đang có bản chờ do LLM đọc: OK → ghi sổ, Sai → hủy. None = tin này không phải trả lời."""
    waiting = confirm.find_waiting(session, row.chat_id)
    if waiting is None:
        return None
    word = fold(row.text or "")
    if word not in CONFIRM_WORDS:  # tin khác kết thúc bản chờ, rồi xử lý như tin bình thường
        confirm.resolve(waiting, "expired", now)
        return None
    if waiting.expires_at <= now:
        confirm.resolve(waiting, "expired", now)
        inbox.finish(row, "done", now, ROUTE_LLM_EXPIRED)
        return [replies.pending_expired()]
    if word == WORD_NO:
        confirm.resolve(waiting, "rejected", now)
        inbox.finish(row, "done", now, ROUTE_LLM_REJECTED)
        return [replies.pending_rejected()]
    answer: list[Reply] = []
    _write_pending(session, waiting, staff, now, answer)
    inbox.finish(row, "done", now, ROUTE_ANSWER)
    return answer


def _write_pending(
    session: Session, waiting: PendingAction, staff: Staff, now: datetime, answer: list[Reply]
) -> None:
    """Nhân viên đã OK: ghi phiếu LLM vào sổ, route kết quả nằm trên tin gốc."""
    origin = session.get(InboundRow, waiting.inbound_id)
    phieu = confirm.phieu_from_json(waiting.parsed)
    result = ledger.record(
        session,
        phieu,
        staff=staff,
        inbound_id=origin.id,
        raw_message=origin.text,
        sent_at=origin.sent_at or origin.received_at,
        now=now,
        source=waiting.parser_source,
    )
    confirm.resolve(waiting, "confirmed", now)
    origin.route = result.route
    if reply := replies.ledger_result(phieu, result):
        answer.append(reply)


async def _ask_llm(
    session: Session, row: InboundRow, staff: Staff, now: datetime, llm: LlmParser | None
) -> list[Reply] | None:
    """Nhờ LLM đọc tin regex bó tay. Đọc được → lưu bản chờ, hỏi OK/Sai (chưa ghi sổ).

    None = LLM tắt hoặc không đọc được → dùng câu trả lời của regex.
    """
    phieu = await llm.parse(row.text or "", now) if llm else None
    if phieu is None:
        return None
    confirm.create(
        session, staff=staff, chat_id=row.chat_id, inbound_id=row.id, phieu=phieu, source="llm", now=now
    )
    return [replies.llm_confirm(phieu, [resolve(line) for line in phieu.lines])]


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
