"""Đồ giả dùng chung cho test — thay ZaloClient và Gemini ở ranh giới ngoài, không gọi dịch vụ thật."""

from datetime import datetime

from langchain_core.messages import AIMessage, BaseMessage

from app.parser.llm import UNREADABLE, LlmRead
from app.parser.regex import Phieu


class FakeSender:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def send_chat_action(self, chat_id: str, action: str = "typing") -> dict:
        self.calls.append(("action", chat_id, action))
        return {}

    async def send_message(self, chat_id: str, text: str, parse_mode: str | None = None) -> dict:
        self.calls.append(("message", chat_id, text, parse_mode))
        return {}

    def messages(self) -> list[str]:
        return [call[2] for call in self.calls if call[0] == "message"]


class FakeLlm:
    """Thay GeminiParser. Phieu → đọc được phiếu; None → tin rác ("khac"); LlmRead → trả nguyên như vậy."""

    def __init__(self, result: Phieu | LlmRead | None = None) -> None:
        if isinstance(result, Phieu):
            result = LlmRead("phieu", result)
        self.result = result or UNREADABLE
        self.calls: list[str] = []

    async def parse(self, text: str, now: datetime) -> LlmRead:
        self.calls.append(text)
        return self.result


class FakeQa:
    """Thay QaAgent: trả sẵn câu trả lời (None = agent không trả lời được), ghi lại câu hỏi."""

    def __init__(self, reply: str | None = "Kho tổng còn 30 quả trứng.") -> None:
        self.reply = reply
        self.calls: list[dict] = []

    async def answer(self, question: str, *, tenant_id: int, staff_name: str, now: datetime) -> str | None:
        self.calls.append({"question": question, "tenant_id": tenant_id, "staff_name": staff_name})
        return self.reply


class FakeChat:
    """Thay chat model đã bind_tools: trả lần lượt các AIMessage soạn sẵn, ghi lại message mỗi lượt."""

    def __init__(self, *turns: AIMessage | Exception) -> None:
        self.turns = list(turns)
        self.seen: list[list[BaseMessage]] = []

    async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
        self.seen.append(list(messages))
        turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        return turn
