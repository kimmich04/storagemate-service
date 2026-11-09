"""Quyết định trả lời gì cho một tin nhắn — thuần logic, không FastAPI, không I/O.

Trả Outcome: các câu trả lời + phiếu đã chốt (nếu có) để worker ghi sổ. Ghi sổ không nằm ở đây.
"""

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime

from app.channels.base import InboundMessage, Reply
from app.messaging import replies
from app.messaging.pending import PendingQuestion, PendingStore
from app.parser.catalog import resolve
from app.parser.normalize import fold
from app.parser.regex import Phieu, RawLine, parse_phieu

ANSWERS = {"a", "b", "c"}
MENU_WORDS = {"menu", "?"}
HELP_WORDS = {"3", "huong dan"}
WORD_OK, WORD_NO = "ok", "sai"
CONFIRM_WORDS = {WORD_OK, WORD_NO}
TEXT_ONLY_EVENTS = {"sticker", "voice", "unsupported", "other"}

ROUTE_OTHER = "other"
ROUTE_WAITING = "phieu_waiting"  # đang hỏi A/B/C dòng trùng
ROUTE_ANSWER = "phieu_answer"  # tin này là câu trả lời A/B/C
ROUTE_PHIEU = "phieu"  # phiếu đã chốt; worker thay bằng route của kết quả ghi sổ


@dataclass(frozen=True)
class Outcome:
    replies: list[Reply]
    route: str = ROUTE_OTHER
    phieu: Phieu | None = None  # đã chốt, cần ghi sổ
    origin: InboundMessage | None = None  # tin chứa phiếu gốc (khác tin hiện tại khi chốt bằng A/C)
    wants_llm: bool = (
        False  # regex không đọc được dòng hàng nào: worker thử LLM; không được thì dùng `replies` này
    )


def handle(msg: InboundMessage, now: datetime, pending: PendingStore) -> Outcome:
    question = pending.pop(msg.chat_id, now)
    folded = fold(msg.text or "")
    if question and folded in ANSWERS:
        return _answer(question, folded, now, pending)
    if msg.event in TEXT_ONLY_EVENTS:
        return Outcome([replies.text_only()])
    if msg.event == "image":
        if not msg.text:
            return Outcome([replies.photo_only()])
        outcome = _handle_text(msg, folded, now, pending)
        return replace(outcome, replies=[replies.photo_received(), *outcome.replies])
    return _handle_text(msg, folded, now, pending)


def _handle_text(msg: InboundMessage, folded: str, now: datetime, pending: PendingStore) -> Outcome:
    if folded in MENU_WORDS:
        return Outcome([replies.menu()])
    if folded in CONFIRM_WORDS:  # có bản chờ thì worker đã xử lý trước khi tới đây
        return Outcome([replies.nothing_pending()])
    if folded == "1":
        return Outcome(replies.template_out(now))
    if folded == "2":
        return Outcome(replies.template_in(now))
    if folded in HELP_WORDS:
        return Outcome([replies.help_text()])
    phieu = parse_phieu(msg.text or "", msg.sent_at)
    if phieu is None:
        return Outcome([replies.unknown()], wants_llm=True)
    outcome = _phieu_outcome(phieu, msg, now, pending)
    # Có chữ nhập/xuất nhưng không đọc được dòng hàng nào (tin tự do một dòng): thử LLM trước
    return replace(outcome, wants_llm=True) if not phieu.lines else outcome


def _phieu_outcome(phieu: Phieu, origin: InboundMessage, now: datetime, pending: PendingStore) -> Outcome:
    """Tóm tắt phiếu; còn dòng trùng thì hỏi A/B/C từng nhóm một, hết trùng thì phiếu đã chốt."""
    result = [replies.summary(phieu, [resolve(line) for line in phieu.lines])]
    group = _first_duplicate_group(phieu.lines)
    if group:
        pending.put(origin.chat_id, phieu, group, now, origin)
        result.append(replies.duplicate_question(group, phieu.lines[group[0]]))
        return Outcome(result, ROUTE_WAITING)
    return Outcome(result, ROUTE_PHIEU, phieu=phieu, origin=origin)


def _answer(question: PendingQuestion, answer: str, now: datetime, pending: PendingStore) -> Outcome:
    if answer == "b":
        return Outcome([replies.resend_request()], ROUTE_ANSWER)
    lines = question.phieu.lines
    first, *others = question.group
    kept = (
        replace(lines[first], qty=lines[first].qty * len(question.group)) if answer == "a" else lines[first]
    )
    new_lines = [kept if index == first else line for index, line in enumerate(lines) if index not in others]
    return _phieu_outcome(replace(question.phieu, lines=new_lines), question.origin, now, pending)


def _first_duplicate_group(lines: list[RawLine]) -> tuple[int, ...] | None:
    """Dòng trùng = cùng tên (đã fold), cùng số lượng, cùng đơn vị."""
    groups: dict[tuple, list[int]] = defaultdict(list)
    for index, line in enumerate(lines):
        groups[(fold(line.name), line.qty, fold(line.unit or ""))].append(index)
    return next((tuple(group) for group in groups.values() if len(group) > 1), None)
