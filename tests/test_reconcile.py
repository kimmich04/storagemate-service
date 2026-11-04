"""Golden set: tổng số lượng parser đọc từ 118 tin nhắn tháng 10 phải khớp sổ Excel kho tổng."""

import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.parser.catalog import resolve
from app.parser.normalize import fold
from app.parser.regex import Phieu, RawLine, parse_phieu

openpyxl = pytest.importorskip("openpyxl")

EXCEL_PATH = Path(__file__).parent / "fixtures" / "ton_kho_t10.xlsx"
RECEIVED_AT = datetime(2026, 11, 3, 9, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
OCTOBER = 10
MIN_MATCH_RATE = Decimal("0.90")
FIRST_DATA_ROW = 5
NAME_COL, FIRST_DAY_COL, DAYS = 1, 3, 31
IN_SHEET = "TỔNG NHẬP"
SHEET_BY_DESTINATION = {
    "kho 220": "XUẤT KHO 220",
    "đối tác": "XUẤT CHO ĐỐI TÁC-NỘI BỘ",
    "nội bộ": "XUẤT CHO ĐỐI TÁC-NỘI BỘ",
    "Dinh": "XUẤT CHO ĐỐI TÁC-NỘI BỘ",
    "Phú Quốc": "XUẤT CHO PHÚ QUỐC",
}
# Tên dòng Excel mà bộ khớp danh mục không tự đoán đúng (Excel mỗi sheet đặt tên một kiểu).
EXCEL_NAME_OVERRIDES = {
    "hop unity trung": "Unity cà phê Trứng",
    "hop unity ca phe sua": "Unity cà phê sữa đá",
    "unity ca phe 3 vi": "Set 3 vị Unity",
    "bot cold brew hoa tan": "Cold brew coffee",
}
# Nash 03/11: "15 thùng unity" là thật (360 hộp, thiếu vị → bot hỏi); Excel ghi nhầm 15.
KNOWN_EXCEL_ERRORS = {(26, "Unity cà phê Trứng", "XUẤT KHO 220")}

Cell = tuple[int, str, str]  # (ngày, tên hàng trong danh mục, sheet)


def _excel_item_name(raw_name: str) -> str:
    clean = re.sub(r"\(.*?\)", "", raw_name).strip()
    if override := EXCEL_NAME_OVERRIDES.get(fold(clean)):
        return override
    resolved = resolve(RawLine(raw=clean, name=clean, qty=Decimal(1), unit=None, note=None))
    return resolved.item.name if resolved.item else raw_name


def _excel_cells() -> dict[Cell, Decimal]:
    workbook = openpyxl.load_workbook(EXCEL_PATH, read_only=True, data_only=True)
    cells: dict[Cell, Decimal] = {}
    for sheet in {IN_SHEET, *SHEET_BY_DESTINATION.values()}:
        for row in workbook[sheet].iter_rows(min_row=FIRST_DATA_ROW, values_only=True):
            values = row[FIRST_DAY_COL : FIRST_DAY_COL + DAYS]
            if not row[NAME_COL] or not any(isinstance(v, int | float) and v for v in values):
                continue
            name = _excel_item_name(str(row[NAME_COL]))
            for day, value in enumerate(values, start=1):
                if isinstance(value, int | float) and value:
                    cells[(day, name, sheet)] = Decimal(str(value)).normalize()
    return cells


def _sheet_for(phieu: Phieu) -> str | None:
    return IN_SHEET if phieu.action == "IN" else SHEET_BY_DESTINATION.get(phieu.to_loc)


def _parsed_cells(messages: list[str]) -> dict[Cell, Decimal]:
    totals: dict[Cell, Decimal] = defaultdict(Decimal)
    for text in messages:
        phieu = parse_phieu(text, RECEIVED_AT)
        sheet = _sheet_for(phieu)
        if phieu.date.month != OCTOBER or sheet is None:
            continue
        for line in map(resolve, phieu.lines):
            if line.components:
                parts = line.components
            elif line.item and line.qty_base is not None:
                parts = [(line.item.name, line.qty_base)]
            else:
                parts = []
            for name, qty in parts:
                totals[(phieu.date.day, name, sheet)] += qty
    return {cell: qty.normalize() for cell, qty in totals.items()}


def test_october_messages_match_excel_ledger(real_messages: list[str]) -> None:
    if not EXCEL_PATH.exists():
        pytest.skip("thiếu tests/fixtures/ton_kho_t10.xlsx (dữ liệu thật, không commit)")
    expected = {cell: v for cell, v in _excel_cells().items() if cell not in KNOWN_EXCEL_ERRORS}
    parsed = _parsed_cells(real_messages)

    mismatches = {cell: (v, parsed.get(cell)) for cell, v in expected.items() if parsed.get(cell) != v}
    extras = {
        cell: v for cell, v in parsed.items() if cell not in expected and cell not in KNOWN_EXCEL_ERRORS
    }
    rate = Decimal(len(expected) - len(mismatches)) / len(expected)

    print(f"\nKhớp {len(expected) - len(mismatches)}/{len(expected)} ô Excel = {rate:.1%}")
    for (day, name, sheet), (excel, got) in sorted(mismatches.items()):
        print(f"  LỆCH  {day:>2}/10 · {sheet} · {name}: Excel {excel} · parser {got}")
    for (day, name, sheet), got in sorted(extras.items()):
        print(f"  THỪA  {day:>2}/10 · {sheet} · {name}: parser {got}, Excel trống")
    assert rate >= MIN_MATCH_RATE
