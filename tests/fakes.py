"""Đồ giả dùng chung cho test — thay ZaloClient ở ranh giới gửi tin, không gọi Zalo thật."""


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
