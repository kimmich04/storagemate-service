"""Trang Xuất Kho: /api/transactions/out/* [API-O1..O5] và GET /api/transactions?type=OUT [API-O6].

Chạy trên PostgreSQL thật (dữ liệu demo tháng 10/2026, kho tổng id=1). "Hôm nay" vá cố định = 09/11/2026.
Mọi dòng/đối tác thêm vào chỉ nằm trong transaction rollback của fixture `db` → DB thật không bị đổi.
Mốc dữ liệu tháng 10: 254 lượt xuất = 220 LTT (id 2) 171 + Đối tác/nội bộ (id 4) 73 + Phú Quốc (id 3) 10.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

TODAY = date(2026, 11, 9)
OCT = {"month": "2026-10"}
WAREHOUSE = 1
BRANCH_220, BRANCH_PQ, PARTNER = 2, 3, 4


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.inventory.period.today_in", lambda tz: TODAY)


def _get(http: TestClient, url: str, **params: object) -> dict:
    res = http.get(url, params=params)
    assert res.status_code == 200, res.text
    return res.json()


def _out(http: TestClient, path: str, **params: object) -> dict:
    return _get(http, f"/api/transactions/out/{path}", **params)


def _list(http: TestClient, **params: object) -> dict:
    return _get(http, "/api/transactions", type="OUT", **params)


def _item(db: Session, nth: int = 0) -> int:
    return db.execute(
        text("SELECT item_id FROM current_stock WHERE location_id = :l ORDER BY item_id LIMIT 1 OFFSET :n"),
        {"l": WAREHOUSE, "n": nth},
    ).scalar_one()


def _insert(
    db: Session,
    item: int,
    action: str,
    delta: int,
    at: str,
    dest: int | None = None,
    source: str = "manual",
    reverses: int | None = None,
    note: str | None = None,
) -> int:
    admin = db.execute(text("SELECT id FROM admins ORDER BY id LIMIT 1")).scalar_one()
    return db.execute(
        text("""
            INSERT INTO inventory_log (tenant_id, location_id, item_id, action, qty, unit, qty_base,
                                       delta_base, counterpart_location_id, event_time, admin_id,
                                       parser_source, reverses_id, note)
            VALUES (1, :loc, :item, CAST(:action AS inv_action), :qty, 'x', :qty, :delta, :dest,
                    CAST(:at AS timestamptz), :admin, CAST(:src AS parser_source), :rev, :note)
            RETURNING id
        """),
        {
            "loc": WAREHOUSE,
            "item": item,
            "action": action,
            "qty": abs(delta),
            "delta": delta,
            "dest": dest,
            "at": at,
            "admin": admin,
            "src": source,
            "rev": reverses,
            "note": note,
        },
    ).scalar_one()


def _new_partner(db: Session, code: str, name: str) -> int:
    return db.execute(
        text("""
            INSERT INTO locations (tenant_id, code, name, kind)
            VALUES (1, :code, :name, 'partner') RETURNING id
        """),
        {"code": code, "name": name},
    ).scalar_one()


# ---------- O1: dropdown nơi nhận ----------


def test_destinations_lists_places_with_counts_branches_first(http: TestClient) -> None:
    data = _out(http, "destinations", **OCT)
    assert [(d["id"], d["count"]) for d in data["destinations"]] == [
        (BRANCH_220, 171),
        (BRANCH_PQ, 10),
        (PARTNER, 73),
    ]
    assert [d["kind"] for d in data["destinations"]] == ["branch", "branch", "partner"]
    assert data["unknown"] is None
    assert data["period"] == {"month": "2026-10", "from": "2026-10-01", "to": "2026-10-31"}


def test_destinations_empty_period(http: TestClient) -> None:
    data = _out(http, "destinations")  # tháng 11 chưa có giao dịch
    assert data["destinations"] == []
    assert data["unknown"] is None


def test_destinations_unknown_group_appears_only_when_present(http: TestClient, db: Session) -> None:
    _insert(db, _item(db), "OUT", -3, "2026-10-20 10:00+07", dest=None)
    assert _out(http, "destinations", **OCT)["unknown"] == {"count": 1}


def test_destinations_lists_many_partners(http: TestClient, db: Session) -> None:
    p1 = _new_partner(db, "T_P1", "Đối tác Alpha")
    p2 = _new_partner(db, "T_P2", "Đối tác Beta")
    _insert(db, _item(db), "OUT", -1, "2026-10-20 10:00+07", dest=p1)
    _insert(db, _item(db), "OUT", -1, "2026-10-20 10:00+07", dest=p2)
    names = [d["name"] for d in _out(http, "destinations", **OCT)["destinations"]]
    assert names[:2] == ["220 Lê Thánh Tôn", "Phú Quốc"]  # chi nhánh trước
    assert names[2:] == sorted(names[2:])  # đối tác theo tên
    assert {"Đối tác Alpha", "Đối tác Beta"} <= set(names)


# ---------- O2: tổng lượt (ô A) ----------


def test_total_all_destinations(http: TestClient) -> None:
    assert _out(http, "total", **OCT) == {"count": 254}


def test_total_filters_by_destination_ids(http: TestClient) -> None:
    assert _out(http, "total", destinationId=[BRANCH_220], **OCT)["count"] == 171
    assert _out(http, "total", destinationId=[BRANCH_220, PARTNER], **OCT)["count"] == 244
    assert _out(http, "total", destinationId=[999], **OCT)["count"] == 0


def test_total_explicit_empty_selection_is_zero(http: TestClient) -> None:
    assert _out(http, "total", unknownDestination="false", **OCT)["count"] == 0


def test_total_unknown_flag(http: TestClient, db: Session) -> None:
    _insert(db, _item(db), "OUT", -3, "2026-10-20 10:00+07", dest=None)
    assert _out(http, "total", **OCT)["count"] == 255
    assert _out(http, "total", unknownDestination="true", **OCT)["count"] == 1
    assert _out(http, "total", destinationId=[BRANCH_PQ], unknownDestination="true", **OCT)["count"] == 11


def test_total_respects_day_range(http: TestClient) -> None:
    sub = _out(http, "total", month="2026-10", **{"from": "2026-10-10", "to": "2026-10-12"})["count"]
    assert 0 < sub < 254


# ---------- O3: bảng theo nơi nhận (B) ----------


def test_by_destination_rows(http: TestClient) -> None:
    data = _out(http, "by-destination", **OCT)
    rows = {r["id"]: r for r in data["destinations"]}
    assert [r["id"] for r in data["destinations"]] == [BRANCH_220, PARTNER, BRANCH_PQ]  # số lượt giảm dần
    assert (rows[BRANCH_220]["count"], rows[BRANCH_220]["itemCount"]) == (171, 65)
    assert (rows[PARTNER]["count"], rows[PARTNER]["itemCount"]) == (73, 17)
    assert (rows[BRANCH_PQ]["count"], rows[BRANCH_PQ]["itemCount"]) == (10, 10)
    assert rows[BRANCH_220]["lastDate"] == "2026-10-31"
    assert rows[BRANCH_PQ]["lastDate"] == "2026-10-09"
    assert set(rows[BRANCH_220]) == {"id", "name", "kind", "count", "itemCount", "lastDate"}
    assert data["unknown"] is None


def test_by_destination_limit_and_filter(http: TestClient) -> None:
    assert [r["id"] for r in _out(http, "by-destination", limit=2, **OCT)["destinations"]] == [
        BRANCH_220,
        PARTNER,
    ]
    only = _out(http, "by-destination", destinationId=[BRANCH_PQ], **OCT)["destinations"]
    assert [r["id"] for r in only] == [BRANCH_PQ]


def test_by_destination_unknown_row(http: TestClient, db: Session) -> None:
    _insert(db, _item(db), "OUT", -3, "2026-10-20 10:00+07", dest=None)
    unknown = _out(http, "by-destination", **OCT)["unknown"]
    assert unknown == {"count": 1, "itemCount": 1, "lastDate": "2026-10-20"}
    only = _out(http, "by-destination", unknownDestination="true", **OCT)
    assert only["destinations"] == [] and only["unknown"]["count"] == 1


def test_by_destination_empty_period(http: TestClient) -> None:
    data = _out(http, "by-destination")
    assert data["destinations"] == [] and data["unknown"] is None


# ---------- O4: biểu đồ theo ngày (C) ----------


def test_daily_covers_every_day_and_matches_total(http: TestClient) -> None:
    data = _out(http, "daily", **OCT)
    days = data["days"]
    assert len(days) == 31 and days[0]["date"] == "2026-10-01" and days[-1]["date"] == "2026-10-31"
    assert sum(d["total"] for d in days) == _out(http, "total", **OCT)["count"] == 254
    assert all(d["total"] == sum(d["counts"].values()) for d in days)
    assert [s["key"] for s in data["series"]] == [str(BRANCH_220), str(PARTNER), str(BRANCH_PQ)]
    empty = next(d for d in days if d["total"] == 0)
    assert empty["counts"] == {}


def test_daily_filter_matches_by_destination(http: TestClient) -> None:
    data = _out(http, "daily", destinationId=[BRANCH_PQ], **OCT)
    assert [s["key"] for s in data["series"]] == [str(BRANCH_PQ)]
    assert sum(d["total"] for d in data["days"]) == 10


def test_daily_groups_beyond_five_into_other(http: TestClient, db: Session) -> None:
    item = _item(db)
    extra = [_new_partner(db, f"T_X{i}", f"Đối tác X{i}") for i in range(3)]
    for p in extra:
        _insert(db, item, "OUT", -1, "2026-10-20 10:00+07", dest=p)
    data = _out(http, "daily", **OCT)
    keys = [s["key"] for s in data["series"]]
    assert len(keys) == 6 and keys[-1] == "other"  # 5 nơi nhiều lượt nhất + Khác
    other_total = sum(d["counts"].get("other", 0) for d in data["days"])
    assert other_total == 1  # 6 nơi, 2 nơi ít lượt nhất gộp; đối tác X cùng 1 lượt → 1 nơi bị gộp ngoài top
    assert sum(d["total"] for d in data["days"]) == 257


def test_daily_exactly_five_destinations_has_no_other_series(http: TestClient, db: Session) -> None:
    item = _item(db)
    for i in range(2):  # 3 nơi có sẵn + 2 đối tác mới = đúng 5 nơi
        _insert(db, item, "OUT", -1, "2026-10-20 10:00+07", dest=_new_partner(db, f"T_Y{i}", f"Đối tác Y{i}"))
    data = _out(http, "daily", **OCT)
    keys = [s["key"] for s in data["series"]]
    assert len(keys) == 5 and "other" not in keys
    assert all("other" not in d["counts"] for d in data["days"])
    assert sum(d["total"] for d in data["days"]) == 256


def test_daily_unknown_series(http: TestClient, db: Session) -> None:
    _insert(db, _item(db), "OUT", -3, "2026-10-20 10:00+07", dest=None)
    data = _out(http, "daily", **OCT)
    assert data["series"][-1] == {"key": "unknown", "name": "Chưa rõ nơi nhận", "kind": "unknown"}
    assert next(d for d in data["days"] if d["date"] == "2026-10-20")["counts"]["unknown"] == 1


def test_daily_subrange(http: TestClient) -> None:
    data = _out(http, "daily", month="2026-10", **{"from": "2026-10-10", "to": "2026-10-14"})
    assert [d["date"] for d in data["days"]] == [f"2026-10-{n}" for n in range(10, 15)]


def test_daily_timezone_boundary(http: TestClient, db: Session) -> None:
    item = _item(db)
    day31 = {"month": "2026-10", "from": "2026-10-31", "to": "2026-10-31"}
    before = _out(http, "daily", **day31)["days"][0]["total"]
    _insert(db, item, "OUT", -2, "2026-10-31 23:30+07", dest=BRANCH_220)
    _insert(db, item, "OUT", -2, "2026-11-01 00:30+07", dest=BRANCH_220)
    assert _out(http, "daily", **day31)["days"][0]["total"] == before + 1


# ---------- O5: top mặt hàng (D) ----------


def test_top_items_sorted_by_count_and_matches_raw_sql(http: TestClient, db: Session) -> None:
    items = _out(http, "top-items", **OCT)["items"]
    assert len(items) == 10
    counts = [i["count"] for i in items]
    assert counts == sorted(counts, reverse=True)
    top = items[0]
    raw = db.execute(
        text("""
            SELECT count(*), sum(-delta_base) FROM inventory_log
            WHERE tenant_id = 1 AND location_id = :loc AND action = 'OUT' AND item_id = :i
              AND reverses_id IS NULL AND parser_source <> 'opening'
              AND (event_time AT TIME ZONE 'Asia/Ho_Chi_Minh')::date BETWEEN '2026-10-01' AND '2026-10-31'
        """),
        {"loc": WAREHOUSE, "i": top["itemId"]},
    ).one()
    assert (top["count"], top["qtyBase"]) == (raw[0], float(raw[1]))
    assert set(top) == {"itemId", "code", "name", "unit", "count", "qtyBase"}


def test_top_items_ranks_by_count_not_by_quantity(http: TestClient, db: Session) -> None:
    """15000 (gram) trong 1 lượt không được vượt mặt hàng có nhiều lượt hơn."""
    baseline = _out(http, "top-items", limit=1, **OCT)["items"][0]
    quiet = next(
        i for i in _out(http, "top-items", limit=20, **OCT)["items"] if i["itemId"] != baseline["itemId"]
    )
    _insert(db, quiet["itemId"], "OUT", -15000, "2026-10-20 10:00+07", dest=BRANCH_220)
    after = _out(http, "top-items", limit=1, **OCT)["items"][0]
    assert after["itemId"] == baseline["itemId"]


def test_top_items_ties_are_broken_by_quantity(http: TestClient) -> None:
    """Phó Quốc: 10 mặt hàng, mỗi mặt hàng 1 lượt → đồng hạng theo số lượt, xếp tiếp theo qtyBase giảm dần."""
    items = _out(http, "top-items", destinationId=[BRANCH_PQ], limit=20, **OCT)["items"]
    keys = [(i["count"], i["qtyBase"]) for i in items]
    assert keys == sorted(keys, key=lambda k: (-k[0], -k[1]))


def test_top_items_limit_bounds(http: TestClient) -> None:
    assert len(_out(http, "top-items", limit=3, **OCT)["items"]) == 3
    for bad in (0, 21):
        assert http.get("/api/transactions/out/top-items", params={"limit": bad}).status_code == 422


def test_top_items_destination_filter(http: TestClient) -> None:
    items = _out(http, "top-items", destinationId=[BRANCH_PQ], limit=20, **OCT)["items"]
    assert len(items) == 10 and all(i["count"] == 1 for i in items)  # PQ: 10 lượt, 10 mặt hàng


def test_top_items_empty_period(http: TestClient) -> None:
    assert _out(http, "top-items")["items"] == []


# ---------- O6: danh sách lượt xuất (E) ----------


def test_list_total_matches_other_apis(http: TestClient) -> None:
    data = _list(http, **OCT)
    assert data["total"] == _out(http, "total", **OCT)["count"] == 254
    by_dest = _out(http, "by-destination", **OCT)
    assert data["total"] == sum(r["count"] for r in by_dest["destinations"])
    assert data["period"] == {"month": "2026-10", "from": "2026-10-01", "to": "2026-10-31"}
    assert (data["page"], data["pageSize"]) == (1, 50)


def test_list_page_beyond_end_keeps_the_real_total(http: TestClient) -> None:
    data = _list(http, page=999, **OCT)
    assert data["items"] == [] and data["total"] == 254
    assert _list(http, page=999, q="zzz-khong-co", **OCT)["total"] == 0


def test_list_item_shape_and_order(http: TestClient) -> None:
    items = _list(http, **OCT)["items"]
    assert set(items[0]) == {
        "id", "itemId", "code", "name", "unit", "qty", "eventDate",
        "destinationId", "destinationName", "destinationKind",
    }  # fmt: skip
    keys = [(i["eventDate"], i["id"]) for i in items]
    assert keys == sorted(keys, reverse=True)
    assert all(i["destinationName"] for i in items)


def test_list_destination_filter_matches_by_destination_count(http: TestClient) -> None:
    for dest, expected in ((BRANCH_220, 171), (PARTNER, 73), (BRANCH_PQ, 10)):
        data = _list(http, destinationId=[dest], **OCT)
        assert data["total"] == expected
        assert {i["destinationId"] for i in data["items"]} == {dest}


def test_list_unknown_destination_row(http: TestClient, db: Session) -> None:
    row = _insert(db, _item(db), "OUT", -3, "2026-10-31 18:00+07", dest=None)
    data = _list(http, unknownDestination="true", **OCT)
    assert data["total"] == 1
    item = data["items"][0]
    assert item["id"] == row
    assert (item["destinationId"], item["destinationName"], item["destinationKind"]) == (None, None, None)


def test_list_pagination_covers_all_rows_without_overlap(http: TestClient) -> None:
    seen: list[int] = []
    page = 1
    while True:
        items = _list(http, page=page, pageSize=100, **OCT)["items"]
        seen += [i["id"] for i in items]
        if len(items) < 100:
            break
        page += 1
    assert len(seen) == len(set(seen)) == 254


def test_list_search_and_escape(http: TestClient) -> None:
    name = _list(http, **OCT)["items"][0]["name"]
    hit = _list(http, q=name.upper(), **OCT)
    assert hit["total"] >= 1 and all(name.lower() in i["name"].lower() for i in hit["items"])
    assert _list(http, q="zzz-khong-co", **OCT)["total"] == 0
    assert _list(http, q="%", **OCT)["total"] == 0
    assert _list(http, q="_", **OCT)["total"] == 0
    assert _list(http, q="   ", **OCT)["total"] == 254


def test_list_empty_period(http: TestClient) -> None:
    data = _list(http)
    assert data["total"] == 0 and data["items"] == []


def test_in_list_unaffected_by_destination_params(http: TestClient) -> None:
    plain = _get(http, "/api/transactions", type="IN", **OCT)["total"]
    with_dest = _get(http, "/api/transactions", type="IN", destinationId=[BRANCH_220], **OCT)["total"]
    assert plain == with_dest == 78


# ---------- chung: cặp hủy, dòng cân bằng, loại dòng ----------


@pytest.mark.parametrize("later_month", [False, True])
def test_cancelled_pair_is_excluded_everywhere(http: TestClient, db: Session, later_month: bool) -> None:
    item = _item(db)
    original = _insert(db, item, "OUT", -5, "2026-10-15 10:00+07", dest=BRANCH_PQ)
    assert _list(http, **OCT)["total"] == 255
    cancel_at = "2026-11-02 10:00+07" if later_month else "2026-10-15 10:05+07"
    _insert(db, item, "IN", 5, cancel_at, source="undo", reverses=original)
    assert _list(http, **OCT)["total"] == 254
    assert _out(http, "total", **OCT)["count"] == 254
    assert sum(d["total"] for d in _out(http, "daily", **OCT)["days"]) == 254
    assert (
        next(r for r in _out(http, "by-destination", **OCT)["destinations"] if r["id"] == BRANCH_PQ)["count"]
        == 10
    )
    pq = {d["id"]: d["count"] for d in _out(http, "destinations", **OCT)["destinations"]}
    assert pq[BRANCH_PQ] == 10


def test_only_out_rows_are_counted(http: TestClient, db: Session) -> None:
    item = _item(db)
    _insert(db, item, "IN", 3, "2026-10-15 10:00+07")
    _insert(db, item, "WASTE", -3, "2026-10-15 10:00+07")
    _insert(db, item, "ADJUST", -3, "2026-10-15 10:00+07")
    assert _out(http, "total", **OCT)["count"] == 254


def test_balancing_note_rows_are_skipped(http: TestClient, db: Session) -> None:
    _insert(db, _item(db), "OUT", -5, "2026-10-15 10:00+07", dest=BRANCH_220, note="Thực xuất T10 cân bằng")
    assert _out(http, "total", **OCT)["count"] == 254


# ---------- tham số sai ----------

OUT_PATHS = ["destinations", "total", "by-destination", "daily", "top-items"]
BAD_PERIODS = [
    {"month": "2026-12"},
    {"month": "2026-07"},
    {"month": "bad"},
    {"month": "2026-10", "to": "2026-11-01"},
    {"month": "2026-11", "to": "2026-11-10"},
    {"month": "2026-10", "from": "2026-10-20", "to": "2026-10-10"},
]


@pytest.mark.parametrize("path", OUT_PATHS)
@pytest.mark.parametrize("params", BAD_PERIODS)
def test_out_apis_reject_bad_period(http: TestClient, path: str, params: dict) -> None:
    assert http.get(f"/api/transactions/out/{path}", params=params).status_code == 422


def test_invalid_period_body_for_out_list(http: TestClient) -> None:
    res = http.get("/api/transactions", params={"type": "OUT", "month": "2026-12"})
    assert res.status_code == 422 and res.json()["code"] == "invalid_period"


@pytest.mark.parametrize(
    "params",
    [
        {"pageSize": 201},
        {"pageSize": 0},
        {"page": 0},
        {"page": 100_001},
        {"destinationId": "abc"},
        {"unknownDestination": "maybe"},
    ],
)
def test_out_list_rejects_bad_params(http: TestClient, params: dict) -> None:
    assert http.get("/api/transactions", params={"type": "OUT", **params}).status_code == 422


def test_by_destination_limit_bounds(http: TestClient) -> None:
    for bad in (0, 101):
        assert http.get("/api/transactions/out/by-destination", params={"limit": bad}).status_code == 422
