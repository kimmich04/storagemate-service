"""Đồ giả dùng chung cho test — thay ZaloClient và Gemini ở ranh giới ngoài, không gọi dịch vụ thật."""

from datetime import datetime

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
    """Thay GeminiParser: trả sẵn một Phieu (hoặc None = "chưa hiểu tin"), ghi lại tin đã được hỏi."""

    def __init__(self, phieu: Phieu | None = None) -> None:
        self.phieu = phieu
        self.calls: list[str] = []

    async def parse(self, text: str, now: datetime) -> Phieu | None:
        self.calls.append(text)
        return self.phieu
