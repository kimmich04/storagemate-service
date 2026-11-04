from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.parser.catalog import load_catalog, resolve
from app.parser.regex import parse_line, parse_phieu

RECEIVED_AT = datetime(2026, 11, 3, 9, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
MIN_OK_RATE = Decimal("0.95")


def _resolve(raw: str):
    return resolve(parse_line(raw))


def test_catalog_has_123_items_plus_egg_sets() -> None:
    items = load_catalog()

    assert sum(not item.code.startswith("bo-trung") for item in items) == 123
    assert {item.name for item in items if item.code.startswith("bo-trung")} == {
        "Bộ trứng bãi biển",
        "Bộ trứng đỏ cam",
        "Bộ trứng xanh ngọc",
        "Bộ trứng vàng",
    }


@pytest.mark.parametrize(
    ("raw", "item_name", "qty_base", "base_unit"),
    [
        ("2 thùng cafe trứng hoà tan", "Hộp cà phê trứng sấy thăng hoa", 48, "Hộp"),
        ("Viên nén caramel: 24", "Eggpresso caramel vani", 24, "Thanh"),
        ("1 thùng VN robusta", "Eggpresso Robusta", 24, "Thanh"),
        ("thìa nhựa vàng : 6 gói", "Thìa nhựa vàng", 300, "Cái"),
        ("2 bịch khăn giấy egg yolk", "Giấy ăn vuông eggyolk", 2, "Kg"),
        ("Ống hút nhỏ: 1 thùng", "Ống hút size 6", 3000, "Cái"),
        ("Túi mer nhỏ: 30", "Túi giấy logo nhỏ", 30, "Cái"),
        ("Cốc wall lớn: 3", "Ly café double wall 160ml", 3, "Cái"),
    ],
)
def test_alias_and_unit_conversion(raw: str, item_name: str, qty_base: int, base_unit: str) -> None:
    resolved = _resolve(raw)

    assert resolved.status == "ok"
    assert resolved.item.name == item_name
    assert (resolved.qty_base, resolved.base_unit) == (Decimal(qty_base), base_unit)


def test_vien_nen_is_a_product_name_not_the_unit_vien() -> None:
    resolved = _resolve("5 viên nén houseblend")

    assert resolved.item.name == "Eggpresso House Blend"
    assert (resolved.qty_base, resolved.base_unit) == (Decimal(5), "Thanh")


def test_nap_coc_nhua_thung_is_ambiguous_between_tall_and_short_box() -> None:
    resolved = _resolve("Nắp cốc nhựa: 1 thùng")

    assert resolved.status == "ambiguous"
    assert resolved.item.name == "Nắp cốc nhựa"
    assert resolved.qty_base is None


def test_unknown_size_maps_to_largest_existing_size_with_warning() -> None:
    resolved = _resolve("2 dĩa tròn 22cm")

    assert resolved.item.name == "Đĩa tròn trứng lòng vàng 20cm"
    assert resolved.qty_base == Decimal(2)
    assert "không có size 22cm" in resolved.warning


def test_bot_kem_trung_counts_as_the_tui_item() -> None:
    resolved = _resolve("bột kem trứng: 5")

    assert (resolved.item.code, resolved.base_unit, resolved.qty_base) == ("118", "Túi", Decimal(5))


def test_unity_without_flavour_is_ambiguous_but_still_converted() -> None:
    resolved = _resolve("15 thùng unity")

    assert resolved.status == "ambiguous"
    assert resolved.item is None
    assert (resolved.qty_base, resolved.base_unit) == (Decimal(360), "Hộp")


def test_egg_set_explodes_into_bowl_cup_and_zig() -> None:
    resolved = _resolve("2 bộ trứng màu vàng")

    assert resolved.item.name == "Bộ trứng vàng"
    assert resolved.components == [
        ("Bát trứng ngâm vàng", Decimal(2)),
        ("Cốc trứng có nắp vàng", Decimal(2)),
        ("Zig café vàng", Decimal(2)),
    ]


def test_cup_without_bo_counts_cups_only() -> None:
    resolved = _resolve("cốc 3 màu xanh: 2 ( không có đĩa)")

    assert (resolved.item.name, resolved.qty_base) == ("Cốc sứ 3 màu xanh", Decimal(2))
    assert resolved.components == []


def test_at_least_95_percent_of_fixture_lines_resolve_ok(real_messages: list[str]) -> None:
    lines = [line for text in real_messages for line in parse_phieu(text, RECEIVED_AT).lines]
    statuses = [resolve(line).status for line in lines]

    assert len(statuses) == 328
    assert Decimal(statuses.count("ok")) / len(statuses) >= MIN_OK_RATE
