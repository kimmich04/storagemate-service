"""Câu hỏi A/B/C đang chờ nhân viên trả lời, theo từng chat."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.channels.base import InboundMessage
from app.parser.regex import Phieu

PENDING_TTL = timedelta(minutes=10)


@dataclass(frozen=True)
class PendingQuestion:
    phieu: Phieu
    group: tuple[int, ...]  # vị trí (0-based) các dòng trùng nhau trong phieu.lines
    expires_at: datetime
    origin: InboundMessage  # tin chứa phiếu gốc — sổ trỏ về tin này, không phải tin "a"/"c"


class PendingStore:
    # ponytail: dict trong RAM, mất khi restart worker; đúng vì chỉ có 1 worker.
    # Bền hơn: bảng pending_actions.
    def __init__(self) -> None:
        self._questions: dict[str, PendingQuestion] = {}

    def put(
        self, chat_id: str, phieu: Phieu, group: tuple[int, ...], now: datetime, origin: InboundMessage
    ) -> None:
        self._questions[chat_id] = PendingQuestion(phieu, group, now + PENDING_TTL, origin)

    def pop(self, chat_id: str, now: datetime) -> PendingQuestion | None:
        """Lấy và xoá luôn — tin tiếp theo dù là gì cũng kết thúc câu hỏi cũ."""
        question = self._questions.pop(chat_id, None)
        return question if question and question.expires_at > now else None
