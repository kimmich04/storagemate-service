import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.channels.base import EventKind, InboundMessage, Reply
from app.messaging.dispatcher import handle
from app.messaging.pending import PendingStore

NOW = datetime(2026, 11, 3, 9, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
NUMBERED_LINE = re.compile(r"^\d+\. ", flags=re.MULTILINE)


def _msg(text: str | None, event: EventKind = "text", photo_url: str | None = None) -> InboundMessage:
    return InboundMessage(
        channel="zalo",
        message_id="m1",
        chat_id="chat-1",
        sender_id="user-1",
        display_name="Nhân viên",
        event=event,
        text=text,
        photo_url=photo_url,
        sent_at=NOW,
    )


def _all_text(replies: list[Reply]) -> str:
    return "\n".join(reply.text for reply in replies)


@pytest.fixture
def pending() -> PendingStore:
    return PendingStore()


@pytest.mark.parametrize("text", ["menu", "Menu", "?"])
def test_menu_offers_three_numbered_choices(text: str, pending: PendingStore) -> None:
    replies = handle(_msg(text), NOW, pending)

    assert len(replies) == 1
    assert replies[0].quick_replies == ["Mẫu Xuất", "Mẫu Nhập", "Hướng dẫn"]


def test_choice_1_sends_lead_line_then_xuat_template_dated_today(pending: PendingStore) -> None:
    replies = handle(_msg("1"), NOW, pending)

    assert len(replies) == 2
    assert replies[1].text.startswith("ngày 03/11 xuất từ kho tổng sang kho 220")


def test_choice_2_sends_nhap_template(pending: PendingStore) -> None:
    replies = handle(_msg("2"), NOW, pending)

    assert replies[1].text.startswith("ngày 03/11 nhập hàng về kho tổng")


@pytest.mark.parametrize("text", ["3", "hướng dẫn"])
def test_choice_3_sends_help(text: str, pending: PendingStore) -> None:
    replies = handle(_msg(text), NOW, pending)

    assert "Tên hàng: số lượng" in _all_text(replies)


def test_phieu_gets_numbered_summary_marked_as_trial(real_messages: list[str], pending: PendingStore) -> None:
    replies = handle(_msg(real_messages[10]), NOW, pending)

    assert len(replies) == 1
    assert len(NUMBERED_LINE.findall(replies[0].text)) == 14
    assert "🧪 Bản thử" in replies[0].text


def test_duplicate_lines_ask_a_b_c(real_messages: list[str], pending: PendingStore) -> None:
    replies = handle(_msg(real_messages[73]), NOW, pending)

    assert "❓ Dòng 2 và 3" in _all_text(replies)


def test_answer_a_merges_duplicates(real_messages: list[str], pending: PendingStore) -> None:
    handle(_msg(real_messages[73]), NOW, pending)

    replies = handle(_msg("a"), NOW + timedelta(minutes=1), pending)

    assert "Giấy ăn vuông eggyolk — 4 bịch (= 4 kg)" in _all_text(replies)


def test_answer_c_keeps_one_line(real_messages: list[str], pending: PendingStore) -> None:
    handle(_msg(real_messages[73]), NOW, pending)

    text = _all_text(handle(_msg("C"), NOW + timedelta(minutes=1), pending))

    assert "Giấy ăn vuông eggyolk — 2 bịch (= 2 kg)" in text
    assert len(NUMBERED_LINE.findall(text)) == 2


def test_answer_b_asks_to_resend_with_distinct_names(real_messages: list[str], pending: PendingStore) -> None:
    handle(_msg(real_messages[73]), NOW, pending)

    replies = handle(_msg("b"), NOW + timedelta(minutes=1), pending)

    assert "gõ lại phiếu" in _all_text(replies)


def test_answer_after_ten_minutes_is_treated_as_normal_text(
    real_messages: list[str], pending: PendingStore
) -> None:
    handle(_msg(real_messages[73]), NOW, pending)

    replies = handle(_msg("a"), NOW + timedelta(minutes=11), pending)

    assert "chưa hiểu" in _all_text(replies)


def test_sticker_gets_text_only_hint(pending: PendingStore) -> None:
    replies = handle(_msg(None, event="sticker"), NOW, pending)

    assert "chỉ đọc được tin nhắn chữ" in _all_text(replies)


def test_photo_without_caption_gets_photo_hint(pending: PendingStore) -> None:
    replies = handle(_msg(None, event="image", photo_url="https://example.test/a.jpg"), NOW, pending)

    assert "chú thích" in _all_text(replies)


def test_photo_with_phieu_caption_gets_summary(real_messages: list[str], pending: PendingStore) -> None:
    replies = handle(
        _msg(real_messages[10], event="image", photo_url="https://example.test/a.jpg"), NOW, pending
    )

    text = _all_text(replies)
    assert "📷" in text
    assert "🧪 Bản thử" in text


def test_unknown_text_gets_hint_and_menu(pending: PendingStore) -> None:
    replies = handle(_msg("hello"), NOW, pending)

    assert "chưa hiểu" in _all_text(replies)
    assert replies[-1].quick_replies == ["Mẫu Xuất", "Mẫu Nhập", "Hướng dẫn"]


def test_line_with_question_mark_tells_staff_how_to_fix(pending: PendingStore) -> None:
    replies = handle(_msg("ngày 26/10 xuất từ kho tổng sang kho 220\n\t15 thùng unity"), NOW, pending)

    assert "👉 Sửa dòng có ❓" in _all_text(replies)
