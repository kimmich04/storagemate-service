"""Quyết định trả lời gì cho một tin nhắn — thuần logic, không FastAPI, không I/O. Pha DB: worker gọi."""

from collections import defaultdict
from dataclasses import replace
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
TEXT_ONLY_EVENTS = {"sticker", "voice", "unsupported", "other"}


def handle(msg: InboundMessage, now: datetime, pending: PendingStore) -> list[Reply]:
    question = pending.pop(msg.chat_id, now)
    folded = fold(msg.text or "")
    if question and folded in ANSWERS:
        return _answer(question, folded, msg.chat_id, now, pending)
    if msg.event in TEXT_ONLY_EVENTS:
        return [replies.text_only()]
    if msg.event == "image":
        if not msg.text:
            return [replies.photo_only()]
        return [replies.photo_received(), *_handle_text(msg, folded, now, pending)]
    return _handle_text(msg, folded, now, pending)


def _handle_text(msg: InboundMessage, folded: str, now: datetime, pending: PendingStore) -> list[Reply]:
    if folded in MENU_WORDS:
        return [replies.menu()]
    if folded == "1":
        return replies.template_out(now)
    if folded == "2":
        return replies.template_in(now)
    if folded in HELP_WORDS:
        return [replies.help_text()]
    phieu = parse_phieu(msg.text or "", msg.sent_at)
    if phieu is None:
        return [replies.unknown()]
    return _phieu_replies(phieu, msg.chat_id, now, pending)


def _phieu_replies(phieu: Phieu, chat_id: str, now: datetime, pending: PendingStore) -> list[Reply]:
    """Tóm tắt phiếu; còn dòng trùng thì hỏi A/B/C từng nhóm một."""
    result = [replies.summary(phieu, [resolve(line) for line in phieu.lines])]
    group = _first_duplicate_group(phieu.lines)
    if group:
        pending.put(chat_id, phieu, group, now)
        result.append(replies.duplicate_question(group, phieu.lines[group[0]]))
    return result


def _answer(
    question: PendingQuestion, answer: str, chat_id: str, now: datetime, pending: PendingStore
) -> list[Reply]:
    if answer == "b":
        return [replies.resend_request()]
    lines = question.phieu.lines
    first, *others = question.group
    kept = (
        replace(lines[first], qty=lines[first].qty * len(question.group)) if answer == "a" else lines[first]
    )
    new_lines = [kept if index == first else line for index, line in enumerate(lines) if index not in others]
    return _phieu_replies(replace(question.phieu, lines=new_lines), chat_id, now, pending)


def _first_duplicate_group(lines: list[RawLine]) -> tuple[int, ...] | None:
    """Dòng trùng = cùng tên (đã fold), cùng số lượng, cùng đơn vị."""
    groups: dict[tuple, list[int]] = defaultdict(list)
    for index, line in enumerate(lines):
        groups[(fold(line.name), line.qty, fold(line.unit or ""))].append(index)
    return next((tuple(group) for group in groups.values() if len(group) > 1), None)
