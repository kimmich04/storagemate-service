"""Adapter kênh Zalo: payload Zalo ⇄ InboundMessage / Reply. Không gọi mạng."""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.channels.base import EventKind, InboundMessage, Reply
from app.config import settings

CHANNEL = "zalo"
MAX_TEXT_LENGTH = 2000  # giới hạn text của sendMessage
MS_PER_SECOND = 1000
UNSUPPORTED_EVENT = "message.unsupported.received"
EVENT_BY_MESSAGE_TYPE: dict[str, EventKind] = {
    "CHAT_TEXT": "text",
    "CHAT_PHOTO": "image",
    "CHAT_STICKER": "sticker",
    "CHAT_VOICE": "voice",
}
MENU_HEADER = "📋 Chọn nhanh (gõ số):"
LOCAL_TZ = ZoneInfo(settings.TZ)


def parse_update(payload: dict) -> InboundMessage | None:
    """Nhận cả body webhook `{event_name, message}` lẫn getUpdates `{ok, result}`; thiếu field → None."""
    event = payload.get("result", payload)
    message = event.get("message") if isinstance(event, dict) else None
    if not isinstance(message, dict):
        return None
    try:
        message_id, chat_id, date_ms = message["message_id"], message["chat"]["id"], message["date"]
        sent_at = datetime.fromtimestamp(int(date_ms) / MS_PER_SECOND, tz=LOCAL_TZ)
    except (KeyError, TypeError, ValueError):
        return None
    sender = message.get("from") or {}
    kind: EventKind = (
        "unsupported"
        if event.get("event_name") == UNSUPPORTED_EVENT
        else EVENT_BY_MESSAGE_TYPE.get(message.get("message_type", ""), "other")
    )
    return InboundMessage(
        channel=CHANNEL,
        message_id=str(message_id),
        chat_id=str(chat_id),
        sender_id=str(sender.get("id", "")),
        display_name=str(sender.get("display_name", "")),
        event=kind,
        text=message.get("caption") if kind == "image" else message.get("text"),
        photo_url=message.get("photo_url"),
        sent_at=sent_at,
    )


def render(reply: Reply) -> list[str]:
    """Zalo không có nút → quick replies thành danh sách đánh số; cắt tin dài theo dòng, mỗi phần ≤ 2000."""
    text = reply.text
    if reply.quick_replies:
        options = "\n".join(
            f"{number} · {label}" for number, label in enumerate(reply.quick_replies, start=1)
        )
        text = f"{text}\n\n{MENU_HEADER}\n{options}"
    return _split(text)


def save_sample(payload: dict, directory: str | Path = settings.ZALO_SAMPLES_DIR) -> None:
    """Ghi payload thô (mỗi dòng một JSON) để tra tên field thật của Zalo trong Pha 0."""
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{datetime.now(LOCAL_TZ):%Y-%m-%d}.jsonl"
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _split(text: str) -> list[str]:
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        while len(line) > MAX_TEXT_LENGTH:  # một dòng quá dài: cắt cứng
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:MAX_TEXT_LENGTH])
            line = line[MAX_TEXT_LENGTH:]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > MAX_TEXT_LENGTH:
            chunks.append(current)
            candidate = line
        current = candidate
    if current:
        chunks.append(current)
    return chunks
