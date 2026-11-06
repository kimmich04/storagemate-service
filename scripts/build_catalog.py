"""Sinh app/parser/catalog.json từ bảng danh mục đã duyệt (sheet "Quy đổi đơn vị").

Chạy: python scripts/build_catalog.py data/catalog/storagemate-don-vi-va-ten-goi.xlsx
Pha DB: cùng dữ liệu này seed bảng items + units.
"""

import json
import sys
from pathlib import Path

import openpyxl

SHEET = "Quy đổi đơn vị"
OUTPUT = Path(__file__).resolve().parents[1] / "app" / "parser" / "catalog.json"
UNKNOWN_FACTOR = "?"
# 1 set trứng = 1 bát ngâm + 1 cốc trứng có nắp + 1 zig (không gồm khay gỗ). Danh mục không có cốc
# "bãi biển" → bộ bãi biển dùng cốc nắp be (phiếu 11/10 xuất đúng bộ ba này).
EGG_SETS = {
    "bãi biển": ("Bát trứng ngâm bãi biển", "Cốc trứng có nắp be", "Zig café bãi biển"),
    "đỏ cam": ("Bát trứng ngâm đỏ cam", "Cốc trứng có nắp đỏ cam", "Zig café đỏ cam"),
    "xanh ngọc": ("Bát trứng ngâm xanh ngọc", "Cốc trứng có nắp xanh ngọc", "Zig café xanh ngọc"),
    "vàng": ("Bát trứng ngâm vàng", "Cốc trứng có nắp vàng", "Zig café vàng"),
}
# 1 bộ = 1 cốc + 1 đĩa, chỉ tách khi nhân viên ghi "bộ". Capu / 3 màu xanh: sheet Quy cách ghi rõ đĩa;
# Espresso / Hoàng hôn / Bình minh: sheet chỉ ghi "1 đĩa" → lấy đĩa nằm ngay dưới cốc trong sheet.
CUP_SAUCERS = {
    "Ly Espresso": "Đĩa kê cốc xanh nhỏ",
    "Cốc sứ Capu, Latte": "Đĩa kê cốc xanh to",
    "Cốc sứ 3 màu xanh": "Đĩa kê cốc be",
    "Cốc Hoàng hôn": "Đĩa kê cốc cam",
    "Cốc Bình minh": "Đĩa kê cốc be",
}


def read_items(xlsx: Path) -> list[dict]:
    rows = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)[SHEET].iter_rows(
        min_row=2, values_only=True
    )
    items: list[dict] = []
    for code, name, base_unit, unit, factor, *_ in rows:
        if code is not None:
            items.append(
                {"code": str(code), "name": str(name).strip(), "base_unit": base_unit, "conversions": {}}
            )
        if unit:
            factor_text = str(factor).strip()
            items[-1]["conversions"][unit] = None if factor_text == UNKNOWN_FACTOR else factor_text
    return items


def add_bundles(items: list[dict]) -> list[dict]:
    code_by_name = {item["name"]: item["code"] for item in items}
    for item in items:
        saucer = CUP_SAUCERS.get(item["name"])
        item["bundle"] = [[item["code"], "1"], [code_by_name[saucer], "1"]] if saucer else []
        item["bundle_needs_bo"] = bool(saucer)
    egg_sets = [
        {
            "code": f"bo-trung-{index}",
            "name": f"Bộ trứng {color}",
            "base_unit": "Bộ",
            "conversions": {},
            "bundle": [[code_by_name[part], "1"] for part in parts],
            "bundle_needs_bo": False,
        }
        for index, (color, parts) in enumerate(EGG_SETS.items(), start=1)
    ]
    return items + egg_sets


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("Cách dùng: python scripts/build_catalog.py <file danh mục .xlsx>")
    items = read_items(Path(sys.argv[1]))
    catalog = add_bundles(items)
    OUTPUT.write_text(json.dumps(catalog, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Đã ghi {OUTPUT.name}: {len(items)} mặt hàng + {len(catalog) - len(items)} bộ trứng")


if __name__ == "__main__":
    main()
