import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.channels.base import Reply
from app.channels.zalo import MAX_TEXT_LENGTH, parse_update, render, save_sample

DATE_MS = 1750316131602  # mẫu trong docs getUpdates


def _event(message_type: str = "CHAT_TEXT", event_name: str = "message.text.received", **fields) -> dict:
    message = {
        "message_id": "2d758cb5e222177a4e35",
        "date": DATE_MS,
        "message_type": message_type,
        "from": {"id": "user-1", "display_name": "Ted", "is_bot": False},
        "chat": {"id": "chat-1", "chat_type": "PRIVATE"},
        **fields,
    }
    return {"event_name": event_name, "message": message}


def test_webhook_body_and_get_updates_body_give_same_message() -> None:
    webhook = _event(text="Xin chào")
    polled = {"ok": True, "result": webhook}

    assert parse_update(webhook) == parse_update(polled)
    msg = parse_update(webhook)
    assert (msg.chat_id, msg.sender_id, msg.display_name, msg.event, msg.text) == (
        "chat-1",
        "user-1",
        "Ted",
        "text",
        "Xin chào",
    )


def test_date_in_milliseconds_becomes_vietnam_time() -> None:
    msg = parse_update(_event(text="hi"))

    expected = datetime.fromtimestamp(DATE_MS / 1000, tz=ZoneInfo("Asia/Ho_Chi_Minh"))
    assert msg.sent_at == expected
    assert msg.sent_at.utcoffset().total_seconds() == 7 * 3600


def test_photo_uses_caption_as_text() -> None:
    payload = _event(
        "CHAT_PHOTO",
        "message.image.received",
        photo_url="https://example.test/p.jpg",
        caption="ngày 3/11 xuất",
    )

    msg = parse_update(payload)

    assert (msg.event, msg.text, msg.photo_url) == ("image", "ngày 3/11 xuất", "https://example.test/p.jpg")


def test_unsupported_user_event_is_marked_unsupported() -> None:
    msg = parse_update(_event("CHAT_TEXT", "message.unsupported.received"))

    assert msg.event == "unsupported"


def test_garbage_payload_is_ignored() -> None:
    assert parse_update({"hello": "world"}) is None
    assert parse_update({"event_name": "message.text.received", "message": {"text": "thiếu id"}}) is None


def test_render_appends_numbered_quick_replies() -> None:
    chunks = render(Reply("Chào bạn", quick_replies=["Mẫu Xuất", "Mẫu Nhập"]))

    assert chunks == ["Chào bạn\n\n📋 Chọn nhanh (gõ số):\n1 · Mẫu Xuất\n2 · Mẫu Nhập"]


def test_long_reply_is_split_on_line_boundaries() -> None:
    lines = [f"{i}. " + "x" * 46 for i in range(50)]  # 50 dòng × ~50 ký tự ≈ 2 500
    chunks = render(Reply("\n".join(lines)))

    assert len(chunks) == 2
    assert all(len(chunk) <= MAX_TEXT_LENGTH for chunk in chunks)
    assert "\n".join(chunks) == "\n".join(lines)


def test_save_sample_appends_one_json_line_per_payload(tmp_path: Path) -> None:
    payload = _event(text="Xin chào")

    save_sample(payload, tmp_path)
    save_sample(payload, tmp_path)

    [sample_file] = list(tmp_path.glob("*.jsonl"))
    rows = sample_file.read_text(encoding="utf-8").splitlines()
    assert [json.loads(row) for row in rows] == [payload, payload]
