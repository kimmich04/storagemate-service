"""Tra dòng hàng vào danh mục tĩnh (catalog.json): tìm mặt hàng, quy về ĐVT gốc, tách bộ.

Pha DB: query bảng items thay cho file JSON.
"""

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Literal

from app.parser.aliases import EXACT_ALIASES, canonical
from app.parser.normalize import fold
from app.parser.regex import RawLine

Status = Literal["ok", "unknown", "ambiguous"]

CATALOG_PATH = Path(__file__).with_name("catalog.json")
MIN_MATCH_SCORE = 0.6  # tỉ lệ token nhân viên gõ có trong tên danh mục
BUNDLE_UNIT = "bo"
TOKEN_RE = re.compile(r"[a-z0-9]+")
SIZE_RE = re.compile(r"^(\d+)(cm|oz|ml|g)$")


@dataclass(frozen=True)
class CatalogItem:
    code: str
    name: str
    base_unit: str
    conversions: dict[str, Decimal | None]  # khoá = fold(đơn vị lớn); None = chưa rõ hệ số, phải hỏi lại
    bundle: tuple[tuple[str, Decimal], ...]  # (mã thành phần, số lượng cho 1 bộ)
    bundle_needs_bo: bool  # cốc chỉ tách bộ khi nhân viên ghi "bộ"
    tokens: frozenset[str]


@dataclass(frozen=True)
class ResolvedLine:
    line: RawLine
    item: CatalogItem | None
    status: Status
    qty_base: Decimal | None
    base_unit: str | None
    components: list[tuple[str, Decimal]]
    warning: str | None


@cache
def load_catalog() -> tuple[CatalogItem, ...]:
    return tuple(_to_item(entry) for entry in json.loads(CATALOG_PATH.read_text(encoding="utf-8")))


def resolve(line: RawLine) -> ResolvedLine:
    candidates, warning = _match(line.name)
    if not candidates:
        return ResolvedLine(line, None, "unknown", None, None, [], None)
    if len(candidates) > 1:
        return _ambiguous(line, candidates)
    item = candidates[0]
    qty_base, base_unit, status, unit_warning = _to_base(item, line)
    warnings = [w for w in (warning, unit_warning) if w]
    return ResolvedLine(
        line=line,
        item=item,
        status=status,
        qty_base=qty_base,
        base_unit=base_unit,
        components=_components(item, line),
        warning="; ".join(warnings) or None,
    )


def _to_item(entry: dict) -> CatalogItem:
    return CatalogItem(
        code=entry["code"],
        name=entry["name"],
        base_unit=entry["base_unit"],
        conversions={
            fold(unit): None if factor is None else Decimal(factor)
            for unit, factor in entry["conversions"].items()
        },
        bundle=tuple((code, Decimal(factor)) for code, factor in entry["bundle"]),
        bundle_needs_bo=entry["bundle_needs_bo"],
        tokens=_tokens(entry["name"]),
    )


@cache
def _by_code() -> dict[str, CatalogItem]:
    return {item.code: item for item in load_catalog()}


def _tokens(name: str) -> frozenset[str]:
    return frozenset(TOKEN_RE.findall(canonical(name)))


def _match(name: str) -> tuple[list[CatalogItem], str | None]:
    """Alias chính xác trước, sau đó chọn mặt hàng chứa nhiều token nhân viên gõ nhất."""
    if code := EXACT_ALIASES.get(fold(name)):
        return [_by_code()[code]], None
    typed = _tokens(name)
    if not typed:
        return [], None
    scored = [(len(typed & item.tokens) / len(typed), item) for item in load_catalog()]
    best = max(score for score, _ in scored)
    if best < MIN_MATCH_SCORE:
        return [], None
    top = [item for score, item in scored if score == best]
    return _pick_size(typed, top) if len(top) > 1 else (top, None)


def _pick_size(typed: frozenset[str], top: list[CatalogItem]) -> tuple[list[CatalogItem], str | None]:
    """Size không có trong danh mục → lấy size lớn hơn gần nhất, không có thì size lớn nhất (Nash 03/11)."""
    typed_size = next((m for token in typed if (m := SIZE_RE.match(token))), None)
    if typed_size is None:
        return top, None
    sized = [
        (int(m[1]), item)
        for item in top
        for token in item.tokens
        if (m := SIZE_RE.match(token)) and m[2] == typed_size[2]
    ]
    if len(sized) != len(top):
        return top, None
    wanted = int(typed_size[1])
    larger = [pair for pair in sized if pair[0] >= wanted]
    _, item = min(larger, key=lambda p: p[0]) if larger else max(sized, key=lambda p: p[0])
    return [item], f"không có size {typed_size[0]}, tạm tính {item.name}"


def _to_base(item: CatalogItem, line: RawLine) -> tuple[Decimal | None, str, Status, str | None]:
    unit = fold(line.unit) if line.unit else None
    if unit is None or unit == fold(item.base_unit) or (unit == BUNDLE_UNIT and item.bundle):
        return line.qty, item.base_unit, "ok", None
    if unit not in item.conversions:
        return line.qty, line.unit, "ok", f"chưa quy đổi được {line.unit} sang {item.base_unit.lower()}"
    factor = item.conversions[unit]
    if factor is None:
        warning = f"chưa rõ 1 {line.unit} {item.name} = bao nhiêu {item.base_unit.lower()}"
        return None, item.base_unit, "ambiguous", warning
    return line.qty * factor, item.base_unit, "ok", None


def _ambiguous(line: RawLine, candidates: list[CatalogItem]) -> ResolvedLine:
    """Chưa rõ loại; nếu mọi ứng viên quy đổi giống nhau thì vẫn tính được số lượng gốc."""
    conversions = {_to_base(item, line)[:2] for item in candidates}
    qty_base, base_unit = conversions.pop() if len(conversions) == 1 else (None, None)
    names = " / ".join(item.name for item in candidates)
    return ResolvedLine(line, None, "ambiguous", qty_base, base_unit, [], f"chưa rõ loại nào: {names}")


def _components(item: CatalogItem, line: RawLine) -> list[tuple[str, Decimal]]:
    says_bo = fold(line.name).startswith(f"{BUNDLE_UNIT} ") or (line.unit and fold(line.unit) == BUNDLE_UNIT)
    if not item.bundle or (item.bundle_needs_bo and not says_bo):
        return []
    return [(_by_code()[code].name, line.qty * factor) for code, factor in item.bundle]
