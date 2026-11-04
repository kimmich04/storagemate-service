"""Tên gọi khác của nhân viên → tên trong danh mục. Pha DB: chuyển sang cột items.aliases.

REWRITES chạy trên chữ đã fold, cho cả tên nhân viên gõ lẫn tên danh mục, để hai bên cùng một cách viết.
"""

import re

from app.parser.normalize import fold

REWRITES = [
    (re.compile(pattern), replacement)
    for pattern, replacement in [
        (r"\bblended\b", "blend"),
        (r"\bhouseblend\b", "house blend"),
        (r"\b(?:vien nen|vn)\b", "eggpresso"),
        (r"\b(?:cf|cafe)\b", "ca phe"),
        (r"\b(?:egg yolk|ey)\b", "eggyolk"),
        (r"\bkhan giay\b", "giay an vuong"),
        (r"\bao thun\b", "ao phong"),
        (r"\bhoa tan\b", "say thang hoa"),
        (r"\bcoldbrew\b", "cold brew"),
        (r"\bbot drip\b", "drip"),
        (r"\bset trung\b", "bo trung"),
        (r"\bba\b", "3"),
        (r"(?<!house )(?<!arabica )\bblend\b", "arabica blend"),
    ]
]

# Đã đối chiếu từng dòng với Excel tháng 10 (sheet "Tên gọi khác", trạng thái ✅). Khoá = fold(tên gõ).
EXACT_ALIASES = {
    "cafe trung hoa tan": "1",
    "cf trung hoa tan": "1",
    "hop cf trung hoa tan": "1",
    "cf trung say": "1",
    "cf trung ey": "1",
    "cf sua ey": "3",
    "coc ba mau do": "11",
    "dia nho 18cm": "31",
    "eggpresso robusta": "55",
    "vien nen robusta": "55",
    "vn robusta": "55",
    "ly wall nho": "66",
    "coc wall nho": "66",
    "ly double wall lon": "67",
    "coc wall lon": "67",
    "set ba vi": "71",
    "set 3 vi": "71",
    "trung su 3 mau": "73",
    "unity 3 vi": "88",
    "thia nhua vang": "97",
    "khan giay egg yolk": "98",
    "khan giay ey": "98",
    "tui mer nho": "104",
    "tui mer to": "105",
    "tui mer lon": "105",
    "ong hut nho": "114",
    "bot kem trung": "118",
    # Sheet gợi ý độ chắc cao; khớp mờ hoà điểm với "Bình ủ coldbrew" (dụng cụ, không phải hàng bán).
    "coldbrew": "85",
    "cold brew": "85",
}


def canonical(name: str) -> str:
    """fold + REWRITES — dạng dùng để so token giữa tên gõ và tên danh mục."""
    text = fold(name)
    for pattern, replacement in REWRITES:
        text = pattern.sub(replacement, text)
    return text
