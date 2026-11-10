from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.parser.regex import parse_line, parse_phieu

RECEIVED_AT = datetime(2026, 11, 3, 9, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))


def test_every_fixture_message_is_a_phieu_with_expected_actions(real_messages: list[str]) -> None:
    phieus = [parse_phieu(text, RECEIVED_AT) for text in real_messages]

    assert len(phieus) == 118
    assert all(p is not None for p in phieus)
    assert sum(p.action == "OUT" for p in phieus) == 95
    assert sum(p.action == "IN" for p in phieus) == 23


def test_fixture_yields_328_item_lines_and_no_bad_lines(real_messages: list[str]) -> None:
    phieus = [parse_phieu(text, RECEIVED_AT) for text in real_messages]

    assert sum(len(p.lines) for p in phieus) == 328
    assert [bad for p in phieus for bad in p.bad_lines] == []


def test_that_ra_la_note_overrides_typed_date() -> None:
    phieu = parse_phieu(
        "13/10 xuất từ kho tổng sang kho 220 ( thật ra là 31/10\n\tViên nén caramel: 24", RECEIVED_AT
    )

    assert phieu.date == date(2026, 10, 31)
    assert phieu.date_note == 'sửa từ 13/10 theo ghi chú "thật ra là"'
    assert phieu.to_loc == "kho 220"
    assert len(phieu.lines) == 1


def test_khi_tong_typo_maps_to_kho_tong_and_size_stays_in_name() -> None:
    phieu = parse_phieu("21/10 xuất từ khi tổng sang kho 220\n\tcốc nhựa 12oz: 1000", RECEIVED_AT)

    assert phieu.from_loc == "kho tổng"
    assert phieu.lines[0].name == "cốc nhựa 12oz"
    assert phieu.lines[0].qty == Decimal(1000)


def test_inline_phieu_takes_item_before_and_route_inside_parentheses() -> None:
    phieu = parse_phieu("ngày 19/10 xuất bột drip: 30 (kho tổng -> 220)", RECEIVED_AT)

    assert phieu.action == "OUT"
    assert (phieu.from_loc, phieu.to_loc) == ("kho tổng", "kho 220")
    assert [(line.name, line.qty) for line in phieu.lines] == [("bột drip", Decimal(30))]


@pytest.mark.parametrize(
    ("raw", "qty", "unit", "name"),
    [
        ("2 dĩa tròn 18cm", 2, None, "dĩa tròn 18cm"),
        ("30 túi mer nhỏ", 30, None, "túi mer nhỏ"),
        ("Unity trứng 15 hộp", 15, "hộp", "Unity trứng"),
        ("5 viên nén houseblend", 5, None, "viên nén houseblend"),
        ("thìa nhựa vàng : 6 gói", 6, "gói", "thìa nhựa vàng"),
        ("48 hộp cafe trứng hoà tan", 48, "hộp", "cafe trứng hoà tan"),
    ],
)
def test_item_line_shapes(raw: str, qty: int, unit: str | None, name: str) -> None:
    line = parse_line(raw)

    assert (line.qty, line.unit, line.name) == (Decimal(qty), unit, name)


def test_note_in_parentheses_is_split_from_item_line() -> None:
    line = parse_line("cốc 3 màu xanh: 2 ( không có đĩa)")

    assert (line.name, line.qty, line.note) == ("cốc 3 màu xanh", Decimal(2), "không có đĩa")


def test_missing_date_uses_received_date_with_note() -> None:
    phieu = parse_phieu("xuất từ kho tổng sang kho 220\n\tDrip: 20", RECEIVED_AT)

    assert phieu.date == RECEIVED_AT.date()
    assert phieu.date_note == "tự lấy ngày / giờ nhận tin"


def test_date_after_tomorrow_belongs_to_previous_year() -> None:
    phieu = parse_phieu("5/11 xuất từ kho tổng sang kho 220\n\tDrip: 20", RECEIVED_AT)

    assert phieu.date == date(2025, 11, 5)


def test_text_without_nhap_or_xuat_is_not_a_phieu() -> None:
    assert parse_phieu("hello", RECEIVED_AT) is None


@pytest.mark.parametrize("text", ["", "   \n\t"])
def test_empty_or_blank_text_is_not_a_phieu(text: str) -> None:
    assert parse_phieu(text, RECEIVED_AT) is None
