"""Chuẩn hoá chữ để so khớp: nhân viên gõ hoa/thường, có/không dấu lẫn lộn."""

import unicodedata


def _fold_char(ch: str) -> str:
    return unicodedata.normalize("NFD", ch.lower().replace("đ", "d"))[0]


def fold_aligned(text: str) -> str:
    """Như fold nhưng giữ nguyên độ dài (text phải là NFC) để cắt lại chữ gốc theo vị trí match."""
    return "".join(_fold_char(ch) for ch in text)


def fold(text: str) -> str:
    """Chữ thường, bỏ dấu, gộp khoảng trắng — dùng chung cho parser và dispatcher."""
    return " ".join(fold_aligned(unicodedata.normalize("NFC", text)).split())
