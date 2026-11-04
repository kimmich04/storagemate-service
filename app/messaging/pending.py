"""Câu hỏi A/B/C đang chờ nhân viên trả lời, theo từng chat. Pha DB: bảng pending_actions."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.parser.regex import Phieu

PENDING_TTL = timedelta(minutes=10)


@dataclass(frozen=True)
class PendingQuestion:
    phieu: Phieu
    group: tuple[int, ...]  # vị trí (0-based) các dòng trùng nhau trong phieu.lines
    expires_at: datetime


class PendingStore:
    # ponytail: dict trong RAM, mất khi restart và chỉ đúng với 1 process; Pha DB chuyển sang Postgres.
    def __init__(self) -> None:
        self._questions: dict[str, PendingQuestion] = {}

    def put(self, chat_id: str, phieu: Phieu, group: tuple[int, ...], now: datetime) -> None:
        self._questions[chat_id] = PendingQuestion(phieu, group, now + PENDING_TTL)

    def pop(self, chat_id: str, now: datetime) -> PendingQuestion | None:
        """Lấy và xoá luôn — tin tiếp theo dù là gì cũng kết thúc câu hỏi cũ."""
        question = self._questions.pop(chat_id, None)
        return question if question and question.expires_at > now else None
