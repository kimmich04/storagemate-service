"""Trang Danh mục hàng hóa: /api/items/locations [D1], /api/items [D2], /api/items/categories [C0] (chỉ đọc).

Chạy trên PostgreSQL thật (dữ liệu demo tháng 10/2026). Test cần sửa dữ liệu (gán Mã VT, thêm tên gọi khác,
lưu trữ mặt hàng) thì làm trong transaction rollback của fixture `db` → DB thật không bị đổi.
Mốc dữ liệu: 359 mặt hàng, 8 nhóm; có sổ ở kho tổng (id 1) 109, ở 220 LTT (id 2) 211, Phú Quốc (id 3) 0;
58 mặt hàng chưa có dòng sổ nào; 58 mặt hàng có quy đổi đóng gói (72 dòng), mặt hàng id 1 = 1 thùng = 40 hộp.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

TOTAL, KHO_TONG, CN_220, CN_PQ, NO_TX = 359, 1, 2, 3, 58


def _get(http: TestClient, url: str, **params: object) -> dict | list:
    res = http.get(url, params=params)
    assert res.status_code == 200, res.text
    return res.json()


def _items(http: TestClient, **params: object) -> dict:
    return _get(http, "/api/items", **params)  # type: ignore[return-value]


def _ledger_items(db: Session, *locs: int) -> set[int]:
    rows = db.execute(
        text("SELECT DISTINCT item_id FROM inventory_log WHERE tenant_id = 1 AND location_id = ANY(:l)"),
        {"l": list(locs)},
    ).all()
    return {r[0] for r in rows}


def _all_ids_page(http: TestClient, page: int, **params: object) -> list[int]:
    return [i["id"] for i in _items(http, page=page, pageSize=150, **params)["items"]]


def _all_ids(http: TestClient, **params: object) -> list[int]:
    return [i["id"] for i in _items(http, pageSize=200, **params)["items"]]


# ---------- D1: kho ----------


def test_locations_lists_warehouse_then_branches_without_partners(http: TestClient) -> None:
    data = _get(http, "/api/items/locations")
    assert [(loc["id"], loc["kind"], loc["itemCount"]) for loc in data["locations"]] == [  # type: ignore[call-overload]
        (KHO_TONG, "warehouse", 109),
        (CN_220, "branch", 211),
        (CN_PQ, "branch", 0),
    ]
    assert data["noTransactionsCount"] == NO_TX  # type: ignore[call-overload]


def test_locations_count_matches_items_filter(http: TestClient) -> None:
    for loc in _get(http, "/api/items/locations")["locations"]:  # type: ignore[call-overload]
        assert _items(http, locationId=loc["id"])["total"] == loc["itemCount"]


def test_archived_items_are_not_counted_in_locations(http: TestClient, db: Session) -> None:
    db.execute(text("UPDATE items SET archived_at = now() WHERE id = 1"))
    data = _get(http, "/api/items/locations")
    assert data["locations"][0]["itemCount"] == 108  # type: ignore[call-overload]


# ---------- D2: bảng ----------


def test_default_returns_every_item(http: TestClient) -> None:
    data = _items(http)
    assert data["total"] == TOTAL
    assert (data["page"], data["pageSize"], len(data["items"])) == (1, 50, 50)
    first = data["items"][0]
    assert set(first) == {"id", "code", "name", "category", "unit", "minQty", "units", "matchedAlias"}
    assert first["matchedAlias"] is None and first["code"] is None
    assert isinstance(first["minQty"], int | float)


def test_sorted_by_name_case_insensitive(http: TestClient, db: Session) -> None:
    names = [i["name"] for i in _items(http, pageSize=200)["items"]]
    db_order = [
        r[0]
        for r in db.execute(
            text("SELECT name FROM items WHERE tenant_id = 1 ORDER BY lower(name), id LIMIT 200")
        )
    ]
    assert names == db_order


def test_pagination_covers_all_rows_without_overlap(http: TestClient) -> None:
    seen: list[int] = []
    for page in range(1, 6):
        seen += [i["id"] for i in _items(http, page=page, pageSize=100)["items"]]
    assert len(seen) == len(set(seen)) == TOTAL


def test_page_beyond_end_is_empty_but_keeps_the_real_total(http: TestClient) -> None:
    data = _items(http, page=999)
    assert data["items"] == [] and data["total"] == TOTAL  # để pager còn đường quay về trang đầu
    assert _items(http, page=999, q="zzz-khong-co")["total"] == 0


def test_filter_by_location_matches_ledger(http: TestClient, db: Session) -> None:
    assert set(_all_ids(http, locationId=KHO_TONG)) == _ledger_items(db, KHO_TONG)
    assert _items(http, locationId=CN_PQ)["total"] == 0


def test_multiple_locations_are_a_union_without_double_counting(http: TestClient, db: Session) -> None:
    union = _ledger_items(db, KHO_TONG, CN_220)
    total = _items(http, locationId=[KHO_TONG, CN_220])["total"]
    ids = [i for p in (1, 2, 3) for i in _all_ids_page(http, p, locationId=[KHO_TONG, CN_220])]
    assert set(ids) == union and len(ids) == len(union) == total < 109 + 211  # chỉ đếm một lần


def test_no_transactions_only(http: TestClient, db: Session) -> None:
    ids = set(_all_ids(http, noTransactions="true"))
    assert len(ids) == NO_TX
    assert ids.isdisjoint(_ledger_items(db, KHO_TONG, CN_220, CN_PQ, 4))


def test_location_plus_no_transactions_is_a_union(http: TestClient) -> None:
    assert _items(http, locationId=KHO_TONG, noTransactions="true")["total"] == 109 + NO_TX


def test_no_transactions_false_is_ignored(http: TestClient) -> None:
    assert _items(http, noTransactions="false")["total"] == TOTAL
    assert _items(http, locationId=KHO_TONG, noTransactions="false")["total"] == 109


def test_category_filter_and_combination(http: TestClient) -> None:
    cats = _get(http, "/api/items/categories")
    name, count = cats[0]["name"], cats[0]["count"]  # type: ignore[call-overload]
    data = _items(http, category=name, pageSize=200)
    assert data["total"] == count and {i["category"] for i in data["items"]} == {name}
    both = _items(http, category=[cats[0]["name"], cats[1]["name"]])["total"]  # type: ignore[call-overload]
    assert both == cats[0]["count"] + cats[1]["count"]  # type: ignore[call-overload]
    assert _items(http, category=name, locationId=CN_PQ)["total"] == 0


# ---------- C0 khớp với bảng ----------


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"locationId": KHO_TONG},
        {"locationId": [KHO_TONG, CN_220]},
        {"noTransactions": "true"},
        {"locationId": KHO_TONG, "noTransactions": "true"},
    ],
)
def test_categories_counts_match_items_table(http: TestClient, params: dict) -> None:
    cats = _get(http, "/api/items/categories", **params)
    assert sum(c["count"] for c in cats) == _items(http, **params)["total"]  # type: ignore[call-overload]
    for c in cats:  # type: ignore[assignment]
        assert _items(http, category=c["name"], **params)["total"] == c["count"]  # type: ignore[call-overload]


def test_item_without_category_stays_in_table_but_not_in_dropdown(http: TestClient, db: Session) -> None:
    """Hiện trạng: dropdown Nhóm hàng chỉ liệt kê nhóm có tên, nên tổng số đếm thấp hơn `total` của bảng."""
    db.execute(text("UPDATE items SET category = NULL WHERE id = 1"))
    assert _items(http)["total"] == TOTAL
    assert sum(c["count"] for c in _get(http, "/api/items/categories")) == TOTAL - 1  # type: ignore[call-overload]
    item = next(i for i in _items(http, pageSize=200)["items"] if i["id"] == 1)
    assert item["category"] is None


def test_categories_without_new_param_behaves_as_before(http: TestClient) -> None:
    cats = _get(http, "/api/items/categories", locationId=KHO_TONG)
    assert sum(c["count"] for c in cats) == 109  # type: ignore[call-overload]


# ---------- tìm kiếm ----------


def test_search_by_name_is_case_insensitive_and_needs_diacritics(http: TestClient) -> None:
    name = _items(http)["items"][0]["name"]
    hit = _items(http, q=name.upper())
    assert hit["total"] >= 1 and all(name.lower() in i["name"].lower() for i in hit["items"])
    assert all(i["matchedAlias"] is None for i in hit["items"])
    assert _items(http, q="zzz-khong-co")["total"] == 0


def test_search_by_code(http: TestClient, db: Session) -> None:
    db.execute(text("UPDATE items SET code = 'ZX-77' WHERE id = 1"))
    data = _items(http, q="zx-77")
    assert [i["id"] for i in data["items"]] == [1] and data["items"][0]["code"] == "ZX-77"
    assert data["items"][0]["matchedAlias"] is None


def test_search_by_alias_reports_matched_alias(http: TestClient, db: Session) -> None:
    db.execute(
        text(
            "INSERT INTO item_aliases (tenant_id, item_id, alias, source, approved) "
            "VALUES (1, 1, 'ten-goi-khac-xyz', 'admin', true)"
        )
    )
    data = _items(http, q="goi-khac-xyz")
    assert [i["id"] for i in data["items"]] == [1]
    assert data["items"][0]["matchedAlias"] == "ten-goi-khac-xyz"


def test_alias_is_not_reported_when_the_name_also_matches(http: TestClient, db: Session) -> None:
    name = next(i["name"] for i in _items(http, pageSize=200)["items"] if i["id"] == 1)
    db.execute(
        text(
            "INSERT INTO item_aliases (tenant_id, item_id, alias, source, approved) "
            "VALUES (1, 1, :alias, 'admin', true)"
        ),
        {"alias": f"{name.lower()} xyz-alias"},
    )
    item = next(i for i in _items(http, q=name.lower())["items"] if i["id"] == 1)
    assert item["matchedAlias"] is None  # khớp theo tên thì không nêu tên gọi khác


def test_search_escapes_wildcards_and_ignores_blank(http: TestClient) -> None:
    # "%" và "_" khớp theo nghĩa đen, không phải ký tự đại diện: chỉ id 285 "SCL đen 70%" chứa "%"
    assert [i["id"] for i in _items(http, q="%")["items"]] == [285]
    assert _items(http, q="_")["total"] == 0
    assert _items(http, q="   ")["total"] == TOTAL


def test_search_respects_location_filter(http: TestClient) -> None:
    name = _items(http, locationId=KHO_TONG)["items"][0]["name"]
    assert _items(http, q=name, locationId=KHO_TONG)["total"] >= 1
    assert _items(http, q=name, locationId=CN_PQ)["total"] == 0


# ---------- quy cách đóng gói ----------


def test_packaging_units_exclude_base_unit_row(http: TestClient) -> None:
    item = next(i for i in _items(http, pageSize=200)["items"] if i["id"] == 1)
    assert item["unit"] == "hộp"
    assert item["units"] == [{"name": "thùng", "factor": 40}]


def test_items_without_conversions_have_empty_units(http: TestClient, db: Session) -> None:
    with_units = db.execute(
        text("""SELECT count(DISTINCT u.item_id) FROM units u JOIN items i ON i.id = u.item_id
                WHERE u.unit_name <> i.base_unit""")
    ).scalar_one()
    rows = [i for p in (1, 2, 3, 4) for i in _items(http, page=p, pageSize=100)["items"]]
    assert sum(1 for i in rows if i["units"]) == with_units == 58
    assert all(u["name"] != i["unit"] for i in rows for u in i["units"])


# ---------- lưu trữ ----------


def test_archived_items_are_hidden_everywhere(http: TestClient, db: Session) -> None:
    db.execute(text("UPDATE items SET archived_at = now() WHERE id = 1"))
    assert _items(http)["total"] == TOTAL - 1
    assert 1 not in _all_ids(http, locationId=KHO_TONG)
    assert sum(c["count"] for c in _get(http, "/api/items/categories")) == TOTAL - 1  # type: ignore[call-overload]


# ---------- tham số sai ----------


@pytest.mark.parametrize(
    "params",
    [
        {"pageSize": 201},
        {"pageSize": 0},
        {"page": 0},
        {"page": 100_001},
        {"locationId": "abc"},
        {"noTransactions": "maybe"},
    ],
)
def test_items_rejects_bad_params(http: TestClient, params: dict) -> None:
    assert http.get("/api/items", params=params).status_code == 422
