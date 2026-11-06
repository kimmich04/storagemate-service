"""Kiểu dữ liệu chung giữa kênh (Zalo, web chat sau này) và lõi xử lý tin nhắn."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

EventKind = Literal["text", "image", "sticker", "voice", "unsupported", "other"]


@dataclass(frozen=True)
class InboundMessage:
    channel: str
    message_id: str
    chat_id: str
    sender_id: str
    display_name: str
    event: EventKind
    text: str | None
    photo_url: str | None
    sent_at: datetime


@dataclass(frozen=True)
class Reply:
    """Một tin trả lời; quick_replies được adapter kênh vẽ thành menu đánh số hoặc nút."""

    text: str
    quick_replies: list[str] = field(default_factory=list)
    parse_mode: str | None = "markdown"
