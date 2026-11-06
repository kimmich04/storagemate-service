"""Đọc phiếu nhập/xuất nhiều dòng đúng như nhân viên đang gõ (tiêu đề + các dòng hàng), chưa tra danh mục.

Mọi regex chạy trên bản fold_aligned (thường, không dấu, cùng độ dài) rồi cắt lại chữ gốc theo vị trí.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from app.parser.normalize import fold, fold_aligned

Action = Literal["IN", "OUT"]

NO_DATE_NOTE = "tự lấy ngày / giờ nhận tin"
UNKNOWN_LOC = "?"
INTERNAL_LOC = "nội bộ"
LOCATION_ALIASES = {
    "kho tong": "kho tổng",
    "khi tong": "kho tổng",
    "220": "kho 220",
    "kho 220": "kho 220",
    "pq": "Phú Quốc",
    "phu quoc": "Phú Quốc",
}
OUT_WORDS = {"xuat", "gui hang"}
# Đơn vị được phép đứng đầu dòng; "túi/set/bộ" đầu dòng là một phần tên hàng (30 túi mer nhỏ).
LEADING_UNITS = {"bich", "hop", "thung", "goi", "thanh", "cai", "pack", "tep", "chai", "lon", "kg"}
TRAILING_UNITS = LEADING_UNITS | {"set", "bo", "tui"}

QTY = r"(?P<qty>\d+(?:[.,]\d+)?)"
DATE_RE = re.compile(r"(\d{1,2})\s*/\s*(\d{1,2})")
CORRECTION_RE = re.compile(r"\(?\s*that ra la\s*(\d{1,2})\s*/\s*(\d{1,2})\s*\)?")
ACTION_RE = re.compile(r"\b(xuat|gui hang|nhap|hang ve)\b")
PAREN_ARROW_RE = re.compile(r"\(([^()]*?)->([^()]*?)\)")
INTERNAL_RE = re.compile(r"\(\s*noi bo\s*\)")
ARROW_RE = re.compile(r"^\s*(?:tu\s+)?(.+?)\s*->\s*(.+?)\s*$")
FROM_TO_RE = re.compile(r"^\s*(?:tu\s+)?(.+?)\s+(?:sang|cho|ra|di)\s+(.+?)\s*$")
FROM_RE = re.compile(r"^\s*tu\s+(.+?)\s*$")
INTO_RE = re.compile(r"^\s*(?:(?:hang\s+)?ve\s+)?(\S.*?)\s*$")
NOTE_RE = re.compile(r"\(([^()]*)\)?\s*$")
COLON_LINE = re.compile(rf"^\s*(?P<name>[^:]+?)\s*:\s*{QTY}\s*(?P<unit>[a-z]+)?\s*$")
TRAILING_LINE = re.compile(rf"^\s*(?P<name>.+?)\s+{QTY}\s*(?P<unit>[a-z]+)\s*$")
LEADING_LINE = re.compile(
    rf"^\s*{QTY}\s+(?:(?P<unit>{'|'.join(sorted(LEADING_UNITS))})\s+)?(?P<name>.+?)\s*$"
)


@dataclass(frozen=True)
class RawLine:
    raw: str
    name: str
    qty: Decimal
    unit: str | None
    note: str | None


@dataclass(frozen=True)
class Phieu:
    action: Action
    date: date
    date_note: str | None
    from_loc: str
    to_loc: str
    lines: list[RawLine]
    bad_lines: list[str]
    warnings: list[str]


def parse_phieu(text: str, received_at: datetime) -> Phieu | None:
    """None khi dòng đầu không có nhập/xuất — tin nhắn này không phải phiếu."""
    lines = unicodedata.normalize("NFC", text).strip().splitlines()
    if not lines:
        return None
    header, *body = lines
    folded = fold_aligned(header)
    correction = CORRECTION_RE.search(folded)
    if correction:
        header, folded = header[: correction.start()], folded[: correction.start()]
    action_match = ACTION_RE.search(folded)
    if action_match is None:
        return None

    action: Action = "OUT" if action_match.group(1) in OUT_WORDS else "IN"
    day, date_note = _resolve_date(folded, correction, received_at)
    from_loc, to_loc, inline_item = _split_route(header[action_match.end() :], action)
    raw_lines = [line.strip() for line in body if line.strip()]
    if not raw_lines and inline_item:
        raw_lines = [inline_item]
    parsed = [(raw, parse_line(raw)) for raw in raw_lines]
    return Phieu(
        action=action,
        date=day,
        date_note=date_note,
        from_loc=from_loc,
        to_loc=to_loc,
        lines=[line for _, line in parsed if line is not None],
        bad_lines=[raw for raw, line in parsed if line is None],
        warnings=[],
    )


def parse_line(raw: str) -> RawLine | None:
    """Thử lần lượt 3 kiểu: `tên: sl [đv]`, `tên sl đv`, `sl [đv] tên`."""
    body, note = _split_note(unicodedata.normalize("NFC", raw))
    folded = fold_aligned(body)
    trailing = TRAILING_LINE.match(folded)
    match = (
        COLON_LINE.match(folded)
        or (trailing if trailing and trailing["unit"] in TRAILING_UNITS else None)
        or LEADING_LINE.match(folded)
    )
    if match is None:
        return None
    unit = body[match.start("unit") : match.end("unit")].lower() if match["unit"] else None
    return RawLine(
        raw=raw,
        name=body[match.start("name") : match.end("name")],
        qty=Decimal(match["qty"].replace(",", ".")),
        unit=unit,
        note=note,
    )


def _split_note(raw: str) -> tuple[str, str | None]:
    match = NOTE_RE.search(raw)
    if match is None:
        return raw, None
    return raw[: match.start()], match.group(1).strip() or None


def _resolve_date(
    folded: str, correction: re.Match[str] | None, received_at: datetime
) -> tuple[date, str | None]:
    typed = DATE_RE.search(folded)
    note = None
    if correction:
        day, month = correction.groups()
        if typed:
            note = f'sửa từ {typed.group(1)}/{typed.group(2)} theo ghi chú "thật ra là"'
    elif typed:
        day, month = typed.groups()
    else:
        return received_at.date(), NO_DATE_NOTE
    try:
        resolved = date(received_at.year, int(month), int(day))
        if resolved > received_at.date() + timedelta(days=1):
            resolved = resolved.replace(year=resolved.year - 1)
    except ValueError:
        return received_at.date(), NO_DATE_NOTE
    return resolved, note


def _split_route(rest: str, action: Action) -> tuple[str, str, str | None]:
    """Trả (từ, đến, chữ còn lại) — chữ còn lại là dòng hàng nếu phiếu viết gọn một dòng."""
    folded = fold_aligned(rest)
    if match := PAREN_ARROW_RE.search(folded):
        return _location(rest, match, 1), _location(rest, match, 2), rest[: match.start()].strip() or None
    if match := INTERNAL_RE.search(folded):
        source = FROM_RE.match(folded, 0, match.start())
        return (_location(rest, source, 1) if source else UNKNOWN_LOC), INTERNAL_LOC, None
    if match := ARROW_RE.match(folded) or FROM_TO_RE.match(folded):
        return _location(rest, match, 1), _location(rest, match, 2), None
    if action == "IN" and (match := INTO_RE.match(folded)):
        return UNKNOWN_LOC, _location(rest, match, 1), None
    return UNKNOWN_LOC, UNKNOWN_LOC, rest.strip() or None


def _location(text: str, match: re.Match[str], group: int) -> str:
    typed = text[match.start(group) : match.end(group)].strip()
    return LOCATION_ALIASES.get(fold(typed), typed)
