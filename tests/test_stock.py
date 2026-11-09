"""Trang Tồn Kho: /api/period, /api/items/categories, /api/stock/*.

Chạy trên PostgreSQL thật (dữ liệu demo tháng 10/2026, kho tổng id=1). Test cần thêm dòng sổ thì chèn
trong transaction rollback của fixture `db` → DB không bị đổi.
"Hôm nay" được vá cố định = 09/11/2026 (autouse) nên kết quả không phụ thuộc đồng hồ máy.
Mốc dữ liệu: tháng 10/2026; 109 mặt hàng; nơi nhận 2 (220), 3 (PQ), 4 (đối tác).
Tồn đầu kỳ nạp ngày 30/09/2026 (parser_source='opening').
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.inventory.exceptions import InvalidPeriodError
from app.inventory.period import resolve_period

TODAY = date(2026, 11, 9)
OCT = {"month": "2026-10"}
OCT_FROM_22 = {"month": "2026-10", "from": "2026-10-22"}
WAREHOUSE = 1


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.inventory.period.today_in", lambda tz: TODAY)


@pytest.fixture(autouse=True)
def require_demo_data(request: pytest.FixtureRequest) -> None:
    """Test dùng DB gắn với dữ liệu demo đã nạp; DB trống thì bỏ qua kèm lý do thay vì lỗi khó hiểu."""
    if "db" not in request.fixturenames:  # test thuần (resolve_period) không cần DB
        return
    db: Session = request.getfixturevalue("db")
    loaded = db.execute(
        text("SELECT count(*) FROM current_stock WHERE location_id = :l"), {"l": WAREHOUSE}
    ).scalar_one()
    if loaded == 0:
        pytest.skip("Cần dữ liệu demo kho tổng (xem scripts/import_excel.py); DB hiện trống")


def _get(http: TestClient, url: str, **params: object) -> dict | list:
    res = http.get(url, params=params)
    assert res.status_code == 200, res.text
    return res.json()


def _all_rows(http: TestClient, **params: object) -> list[dict]:
    return _get(http, "/api/stock", pageSize=200, **params)["items"]  # type: ignore[index]


def _row(http: TestClient, item_id: int, **params: object) -> dict:
    return next(r for r in _all_rows(http, **params) if r["itemId"] == item_id)


def _first_item(db: Session) -> int:
    return db.execute(
        text("SELECT item_id FROM current_stock WHERE location_id = :l ORDER BY item_id LIMIT 1"),
        {"l": WAREHOUSE},
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
) -> int:
    """Chèn một dòng sổ vào kho tổng (`at` là timestamptz, ví dụ '2026-10-15 10:00+07')."""
    admin = db.execute(text("SELECT id FROM admins ORDER BY id LIMIT 1")).scalar_one()
    return db.execute(
        text("""
            INSERT INTO inventory_log (tenant_id, location_id, item_id, action, qty, unit, qty_base,
                                       delta_base, counterpart_location_id, event_time, admin_id,
                                       parser_source, reverses_id)
            VALUES (1, :loc, :item, CAST(:action AS inv_action), :qty, 'x', :qty, :delta, :dest,
                    CAST(:at AS timestamptz), :admin, CAST(:src AS parser_source), :rev)
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
        },
    ).scalar_one()


# ---------- resolve_period: quy tắc kỳ (hàm thuần, không cần DB) ----------


def test_resolve_defaults_to_current_month_until_today() -> None:
    p = resolve_period(date(2026, 11, 9), None, None, None)
    assert (p.month, p.from_, p.to) == ("2026-11", date(2026, 11, 1), date(2026, 11, 9))
    assert (p.min_date, p.max_date) == (date(2026, 11, 1), date(2026, 11, 9))


def test_resolve_past_month_defaults_to_whole_month() -> None:
    p = resolve_period(date(2026, 11, 9), "2026-10", None, None)
    assert (p.from_, p.to, p.max_date) == (date(2026, 10, 1), date(2026, 10, 31), date(2026, 10, 31))


def test_resolve_accepts_any_days_inside_the_month() -> None:
    p = resolve_period(date(2026, 11, 9), "2026-10", date(2026, 10, 3), date(2026, 10, 17))
    assert (p.from_, p.to) == (date(2026, 10, 3), date(2026, 10, 17))


def test_resolve_single_day_range_is_allowed() -> None:
    p = resolve_period(date(2026, 11, 9), "2026-10", date(2026, 10, 15), date(2026, 10, 15))
    assert p.from_ == p.to == date(2026, 10, 15)


def test_resolve_leap_february_and_year_end() -> None:
    assert resolve_period(date(2028, 3, 10), "2028-02", None, None).to == date(2028, 2, 29)
    assert resolve_period(date(2026, 12, 31), None, None, None).to == date(2026, 12, 31)
    assert resolve_period(date(2027, 1, 1), None, None, None).month == "2027-01"


def test_resolve_first_selectable_month_is_august_2026() -> None:
    assert resolve_period(date(2026, 11, 9), "2026-08", None, None).month == "2026-08"
    with pytest.raises(InvalidPeriodError, match="08/2026"):
        resolve_period(date(2026, 11, 9), "2026-07", None, None)


@pytest.mark.parametrize(
    ("month", "from_", "to"),
    [
        ("2026-12", None, None),  # tháng tương lai
        ("2026-11", None, date(2026, 11, 10)),  # đến ngày tương lai
        ("2026-11", date(2026, 11, 10), None),  # từ ngày tương lai
        ("2026-10", date(2026, 9, 30), None),  # từ ngày thuộc tháng trước
        ("2026-10", None, date(2026, 11, 1)),  # đến ngày thuộc tháng sau
        ("2026-10", date(2026, 10, 20), date(2026, 10, 10)),  # từ > đến
        ("2026-08", date(2026, 7, 31), None),  # ngày thuộc 7/2026, trong khi tháng đang chọn là 8/2026
        (None, date(2026, 10, 5), None),  # không truyền month → tháng hiện tại (11), ngày 10/10 ngoài tháng
    ],
)
def test_resolve_rejects_invalid_combinations(month: str | None, from_: date | None, to: date | None) -> None:
    with pytest.raises(InvalidPeriodError):
        resolve_period(date(2026, 11, 9), month, from_, to)


# ---------- [API-P0] GET /api/period ----------


def test_period_default_is_current_month(http: TestClient) -> None:
    body = _get(http, "/api/period")
    assert body["today"] == "2026-11-09" and body["month"] == "2026-11"
    assert (body["from"], body["to"]) == ("2026-11-01", "2026-11-09")
    assert (body["minDate"], body["maxDate"]) == ("2026-11-01", "2026-11-09")


def test_period_months_run_from_august_to_current_month(http: TestClient) -> None:
    months = _get(http, "/api/period")["months"]  # type: ignore[index]
    assert [m["value"] for m in months] == ["2026-08", "2026-09", "2026-10", "2026-11"]
    assert months[0] == {"value": "2026-08", "label": "Tháng 8/2026", "hasData": False}
    # tồn đầu kỳ (30/09) không phải giao dịch → chỉ tháng 10 có dữ liệu
    assert {m["value"]: m["hasData"] for m in months} == {
        "2026-08": False,
        "2026-09": False,
        "2026-10": True,
        "2026-11": False,
    }


def test_period_months_grow_with_the_clock(http: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.inventory.period.today_in", lambda tz: date(2027, 1, 15))
    months = _get(http, "/api/period")["months"]  # type: ignore[index]
    assert [m["value"] for m in months][-3:] == ["2026-11", "2026-12", "2027-01"]
    assert months[-1]["label"] == "Tháng 1/2027"


def test_period_has_data_follows_new_rows(http: TestClient, db: Session) -> None:
    item = _first_item(db)
    _insert(db, item, "IN", 1, "2026-11-05 10:00+07")
    _insert(db, item, "IN", 1, "2026-09-10 10:00+07")
    flags = {m["value"]: m["hasData"] for m in _get(http, "/api/period")["months"]}  # type: ignore[index]
    assert flags["2026-11"] and flags["2026-09"] and flags["2026-10"] and not flags["2026-08"]


def test_period_past_month_defaults_to_whole_month(http: TestClient) -> None:
    body = _get(http, "/api/period", **OCT)
    assert (body["from"], body["to"]) == ("2026-10-01", "2026-10-31")
    assert (body["minDate"], body["maxDate"]) == ("2026-10-01", "2026-10-31")


def test_period_from_and_to_can_be_any_day_in_the_month(http: TestClient) -> None:
    body = _get(http, "/api/period", month="2026-10", **{"from": "2026-10-05", "to": "2026-10-20"})
    assert (body["from"], body["to"]) == ("2026-10-05", "2026-10-20")
    assert (body["minDate"], body["maxDate"]) == ("2026-10-01", "2026-10-31")  # biên chọn vẫn là cả tháng


def test_period_only_from_or_only_to_fills_the_other_side(http: TestClient) -> None:
    only_from = _get(http, "/api/period", month="2026-10", **{"from": "2026-10-20"})
    assert (only_from["from"], only_from["to"]) == ("2026-10-20", "2026-10-31")
    only_to = _get(http, "/api/period", month="2026-10", to="2026-10-15")
    assert (only_to["from"], only_to["to"]) == ("2026-10-01", "2026-10-15")


@pytest.mark.parametrize(
    "params",
    [
        {"month": "2026-07"},  # trước tháng 8/2026
        {"month": "2026-12"},  # tương lai
        {"month": "2026-08", "from": "2026-07-31"},  # ngày thuộc 7/2026 trong khi tháng chọn là 8/2026
        {"month": "2026-10", "from": "2026-09-30"},
        {"month": "2026-10", "to": "2026-11-01"},
        {"month": "2026-11", "to": "2026-11-10"},  # sau hôm nay (09/11)
        {"month": "2026-10", "from": "2026-10-20", "to": "2026-10-10"},
        {"from": "2026-10-05"},  # không có month → tháng 11 hiện tại
    ],
)
def test_period_business_rules_return_422_with_code(http: TestClient, params: dict[str, str]) -> None:
    res = http.get("/api/period", params=params)
    assert res.status_code == 422, res.text
    body = res.json()
    assert body["code"] == "invalid_period" and body["message"]


@pytest.mark.parametrize(
    "params",
    [{"month": "2026-13"}, {"month": "abc"}, {"month": "2026-1"}, {"from": "31-10-2026"}, {"to": "x"}],
)
def test_period_malformed_params_are_422(http: TestClient, params: dict[str, str]) -> None:
    assert http.get("/api/period", params=params).status_code == 422


@pytest.mark.parametrize(
    "url",
    [
        "/api/stock",
        "/api/stock/kpis/total-items",
        "/api/stock/kpis/in-stock",
        "/api/stock/kpis/variance",
        "/api/stock/destinations",
    ],
)
def test_every_stock_endpoint_validates_the_period(http: TestClient, url: str) -> None:
    assert http.get(url, params={"month": "2026-07"}).status_code == 422
    assert http.get(url, params={"month": "2026-10", "from": "2026-11-02"}).status_code == 422
    assert http.get(url, params=OCT).status_code == 200


# ---------- [API-C0] GET /api/items/categories ----------


def test_categories_cover_every_active_item(http: TestClient, db: Session) -> None:
    body = _get(http, "/api/items/categories")
    expected = db.execute(
        text(
            "SELECT count(*) FROM items WHERE tenant_id = 1 AND archived_at IS NULL AND category IS NOT NULL"
        )
    ).scalar_one()
    assert sum(c["count"] for c in body) == expected
    assert len({c["name"] for c in body}) == len(body)  # mỗi nhóm một lần (thứ tự theo collation của DB)
    assert set(body[0]) == {"name", "count"}


def test_categories_by_location_count_items_with_ledger_rows(http: TestClient) -> None:
    body = _get(http, "/api/items/categories", locationId=WAREHOUSE)
    assert sum(c["count"] for c in body) == _get(http, "/api/stock/kpis/total-items")["count"]


def test_categories_union_of_locations_does_not_double_count(http: TestClient) -> None:
    both = _get(http, "/api/items/categories", locationId=[WAREHOUSE, 2])
    everything = _get(http, "/api/items/categories")
    assert sum(c["count"] for c in both) <= sum(c["count"] for c in everything)
    one = _get(http, "/api/items/categories", locationId=WAREHOUSE)
    assert sum(c["count"] for c in both) >= sum(c["count"] for c in one)


# ---------- [API-S1..S3] KPI ----------


def test_kpis_match_the_table(http: TestClient) -> None:
    table = _get(http, "/api/stock", pageSize=1, **OCT)
    assert _get(http, "/api/stock/kpis/total-items", **OCT) == {"count": table["total"]} == {"count": 109}
    in_stock = _get(http, "/api/stock", pageSize=1, status="in_stock", **OCT)["total"]
    assert _get(http, "/api/stock/kpis/in-stock", **OCT) == {"count": in_stock}
    assert _get(http, "/api/stock/kpis/variance", **OCT) == {"count": 0}


def test_kpis_follow_category_and_search_but_not_status(http: TestClient) -> None:
    cat = "MERCHANDISE"
    total = _get(http, "/api/stock/kpis/total-items", category=cat, **OCT)["count"]
    assert total == _get(http, "/api/stock", pageSize=1, category=cat, **OCT)["total"] < 109
    assert _get(http, "/api/stock/kpis/total-items", q="cà phê", **OCT)["count"] == len(
        _all_rows(http, q="cà phê", **OCT)
    )
    # `status` không phải tham số của thẻ: truyền vào cũng không đổi số
    assert _get(http, "/api/stock/kpis/total-items", status="variance", **OCT) == {"count": 109}


def test_variance_kpi_counts_adjust_but_not_opening(http: TestClient, db: Session) -> None:
    item = _first_item(db)
    _insert(db, item, "ADJUST", -3, "2026-10-20 10:00+07")
    assert _get(http, "/api/stock/kpis/variance", **OCT) == {"count": 1}
    rows = _all_rows(http, status="variance", **OCT)
    assert [(r["itemId"], r["variance"]) for r in rows] == [(item, -3.0)]


def test_adjust_before_period_is_not_variance(http: TestClient, db: Session) -> None:
    _insert(db, _first_item(db), "ADJUST", -3, "2026-09-20 10:00+07")
    assert _get(http, "/api/stock/kpis/variance", **OCT) == {"count": 0}


def test_variance_respects_the_day_range(http: TestClient, db: Session) -> None:
    _insert(db, _first_item(db), "ADJUST", -3, "2026-10-20 10:00+07")
    assert _get(http, "/api/stock/kpis/variance", **OCT_FROM_22) == {"count": 0}  # 20/10 nằm trước from
    assert _get(http, "/api/stock/kpis/variance", month="2026-10", to="2026-10-19") == {"count": 0}


def test_month_before_any_data_is_empty(http: TestClient) -> None:
    params = {"month": "2026-08"}  # tồn đầu mới nạp ngày 30/09 nên tháng 8 chưa có mặt hàng nào
    assert _get(http, "/api/stock/kpis/total-items", **params) == {"count": 0}
    assert _get(http, "/api/stock/kpis/in-stock", **params) == {"count": 0}
    assert _get(http, "/api/stock/kpis/variance", **params) == {"count": 0}
    assert _get(http, "/api/stock/destinations", **params) == []
    body = _get(http, "/api/stock", **params)
    assert (body["total"], body["items"]) == (0, [])


def test_month_without_transactions_still_shows_carried_over_stock(http: TestClient) -> None:
    """Tháng 11 chưa có giao dịch nhưng tồn từ tháng 10 vẫn hiển thị (opening = closing)."""
    nov = {"month": "2026-11"}
    oct_rows = {r["itemId"]: r for r in _all_rows(http, **OCT)}
    rows = _all_rows(http, **nov)
    assert len(rows) == 109 == _get(http, "/api/stock/kpis/total-items", **nov)["count"]  # type: ignore[index]
    for r in rows:
        assert r["opening"] == r["closing"] == oct_rows[r["itemId"]]["closing"]
        assert r["inbound"] == r["outboundTotal"] == r["waste"] == r["variance"] == r["other"] == 0
        assert r["outbound"] == {}
    assert _get(http, "/api/stock/destinations", **nov) == []
    assert _get(http, "/api/stock", pageSize=1, onlyMoved="true", **nov)["total"] == 0


def test_opening_balance_dated_inside_the_period_is_opening_not_other(http: TestClient) -> None:
    """Tháng 9: tồn đầu nạp ngày 30/09 nằm trong kỳ nhưng vẫn phải hiện ở cột Tồn đầu, Khác = 0."""
    rows = _all_rows(http, month="2026-09")
    assert len(rows) == 109
    for r in rows:
        assert r["opening"] == r["closing"] and r["other"] == 0
        assert r["inbound"] == r["outboundTotal"] == r["waste"] == r["variance"] == 0
    assert _get(http, "/api/stock", pageSize=1, onlyMoved="true", month="2026-09")["total"] == 0


def test_archived_item_is_hidden_from_table_and_kpis(http: TestClient, db: Session) -> None:
    item = _first_item(db)
    before = _get(http, "/api/stock/kpis/total-items", **OCT)["count"]  # type: ignore[index]
    db.execute(text("UPDATE items SET archived_at = now() WHERE id = :i"), {"i": item})
    assert item not in {r["itemId"] for r in _all_rows(http, **OCT)}
    assert _get(http, "/api/stock/kpis/total-items", **OCT) == {"count": before - 1}


# ---------- [API-S4] GET /api/stock/destinations ----------


def test_destinations_are_known_branches_then_partner(http: TestClient) -> None:
    body = _get(http, "/api/stock/destinations", **OCT)
    assert [(d["id"], d["kind"]) for d in body] == [(2, "branch"), (3, "branch"), (4, "partner")]
    assert set(body[0]) == {"id", "name", "kind"}


def test_destinations_only_list_places_with_exports_in_period(http: TestClient) -> None:
    # từ 22/10 không còn xuất cho PQ (lượt gần nhất của PQ là 15/10)
    ids = [d["id"] for d in _get(http, "/api/stock/destinations", **OCT_FROM_22)]  # type: ignore[union-attr]
    assert 3 not in ids and 2 in ids


def test_destinations_are_dynamic_for_new_partners(http: TestClient, db: Session) -> None:
    partner = db.execute(
        text("""
            INSERT INTO locations (tenant_id, code, name, kind)
            VALUES (1, 'DT_MOI', 'Đối tác A', 'partner') RETURNING id
        """)
    ).scalar_one()
    _insert(db, _first_item(db), "OUT", -2, "2026-10-30 10:00+07", dest=partner)
    body = _get(http, "/api/stock/destinations", **OCT)
    assert [d["kind"] for d in body] == ["branch", "branch", "partner", "partner"]
    assert body[-1]["id"] == partner or body[-2]["id"] == partner


def test_unknown_destination_is_listed_last(http: TestClient, db: Session) -> None:
    item = _first_item(db)
    _insert(db, item, "OUT", -2, "2026-10-30 10:00+07", dest=None)
    body = _get(http, "/api/stock/destinations", **OCT)
    assert body[-1] == {"id": None, "name": "Chưa rõ nơi nhận", "kind": "unknown"}
    assert _row(http, item, **OCT)["outbound"]["null"] == 2.0


def test_destinations_ignore_cancelled_exports(http: TestClient, db: Session) -> None:
    item = _first_item(db)
    original = _insert(db, item, "OUT", -2, "2026-10-30 10:00+07", dest=None)
    _insert(db, item, "IN", 2, "2026-10-30 10:05+07", source="undo", reverses=original)
    assert all(d["id"] is not None for d in _get(http, "/api/stock/destinations", **OCT))  # type: ignore[union-attr]


# ---------- [API-S5] GET /api/stock ----------


def test_response_shape(http: TestClient) -> None:
    body = _get(http, "/api/stock", pageSize=2, **OCT)
    assert set(body) == {"period", "total", "page", "pageSize", "items"}
    assert body["period"] == {"month": "2026-10", "from": "2026-10-01", "to": "2026-10-31"}
    assert (body["page"], body["pageSize"], len(body["items"])) == (1, 2, 2)
    assert set(body["items"][0]) == {
        "itemId", "code", "name", "category", "unit", "opening", "inbound", "outbound",
        "outboundTotal", "waste", "variance", "other", "closing",
    }  # fmt: skip
    assert isinstance(body["items"][0]["closing"], float)


def test_period_block_echoes_normalized_range(http: TestClient) -> None:
    body = _get(http, "/api/stock", pageSize=1, month="2026-10", to="2026-10-15")
    assert body["period"] == {"month": "2026-10", "from": "2026-10-01", "to": "2026-10-15"}


def test_closing_equals_current_stock_view(http: TestClient, db: Session) -> None:
    expected = {
        r[0]: float(r[1])
        for r in db.execute(
            text("SELECT item_id, qty_base FROM current_stock WHERE tenant_id = 1 AND location_id = :l"),
            {"l": WAREHOUSE},
        )
    }
    got = {r["itemId"]: r["closing"] for r in _all_rows(http)}  # mặc định = tháng hiện tại, đến hôm nay
    assert got == expected


def test_stock_identity_and_outbound_total(http: TestClient) -> None:
    for r in _all_rows(http, **OCT):
        rebuilt = r["opening"] + r["inbound"] - r["outboundTotal"] - r["waste"] + r["variance"] + r["other"]
        assert rebuilt == pytest.approx(r["closing"]), r["name"]
        assert sum(r["outbound"].values()) == pytest.approx(r["outboundTotal"]), r["name"]
        assert all(v != 0 for v in r["outbound"].values())


def test_totals_match_the_ledger(http: TestClient, db: Session) -> None:
    rows = _all_rows(http, **OCT)
    sql = """
        SELECT coalesce(sum(abs(delta_base)), 0) FROM inventory_log
        WHERE tenant_id = 1 AND location_id = 1 AND action = :a AND reverses_id IS NULL
          AND (event_time AT TIME ZONE 'Asia/Ho_Chi_Minh')::date BETWEEN '2026-10-01' AND '2026-10-31'
    """
    assert sum(r["inbound"] for r in rows) == pytest.approx(
        float(db.execute(text(sql), {"a": "IN"}).scalar_one())
    )
    assert sum(r["outboundTotal"] for r in rows) == pytest.approx(
        float(db.execute(text(sql), {"a": "OUT"}).scalar_one())
    )
    destinations = {d["id"] for d in _get(http, "/api/stock/destinations", **OCT)}  # type: ignore[union-attr]
    used = {int(k) for r in rows for k in r["outbound"] if k != "null"}
    assert used <= destinations


def test_cancelled_pair_is_removed_from_every_column(http: TestClient, db: Session) -> None:
    item = _first_item(db)
    before = _row(http, item, **OCT)
    original = _insert(db, item, "IN", 5, "2026-10-15 10:00+07")
    _insert(db, item, "OUT", -5, "2026-10-15 10:05+07", source="undo", reverses=original)
    assert _row(http, item, **OCT) == before


def test_cancel_in_a_later_month_still_removes_both_rows(http: TestClient, db: Session) -> None:
    item = _first_item(db)
    before = _row(http, item, **OCT)
    original = _insert(db, item, "IN", 5, "2026-10-15 10:00+07")
    _insert(db, item, "OUT", -5, "2026-11-02 10:00+07", source="undo", reverses=original)
    assert _row(http, item, **OCT) == before


def test_row_after_period_end_is_excluded(http: TestClient, db: Session) -> None:
    item = _first_item(db)
    before = _row(http, item, **OCT)
    _insert(db, item, "IN", 7, "2026-11-01 09:00+07")
    assert _row(http, item, **OCT) == before


def test_timezone_boundary_uses_tenant_day(http: TestClient, db: Session) -> None:
    item = _first_item(db)
    before = _row(http, item, **OCT)
    _insert(db, item, "IN", 7, "2026-10-31 17:30+00")  # = 00:30 ngày 01/11 giờ VN
    assert _row(http, item, **OCT) == before
    nov = _row(http, item, month="2026-11", to="2026-11-01")
    assert nov["inbound"] == 7.0 and nov["opening"] == before["closing"]
    assert nov["closing"] == before["closing"] + 7


def test_late_evening_vn_row_counts_in_its_own_day(http: TestClient, db: Session) -> None:
    item = _first_item(db)
    before = _row(http, item, **OCT)
    _insert(db, item, "IN", 4, "2026-10-31 23:59+07")
    after = _row(http, item, **OCT)
    assert after["inbound"] == before["inbound"] + 4 and after["closing"] == before["closing"] + 4


def test_from_and_to_split_opening_from_movement(http: TestClient, db: Session) -> None:
    item = _first_item(db)
    from12 = {"month": "2026-10", "from": "2026-10-12"}
    before22 = _row(http, item, **OCT_FROM_22)
    before12 = _row(http, item, **from12)
    _insert(db, item, "IN", 9, "2026-10-12 10:00+07")  # trong kỳ từ 12/10, trước kỳ từ 22/10
    r22 = _row(http, item, **OCT_FROM_22)
    r12 = _row(http, item, **from12)
    assert r12["inbound"] == before12["inbound"] + 9
    assert r22["inbound"] == before22["inbound"]  # nằm trước `from` → chỉ làm tăng tồn đầu kỳ
    assert r22["opening"] == before22["opening"] + 9
    assert r22["closing"] == r12["closing"] == before22["closing"] + 9  # tồn cuối chỉ phụ thuộc `to`
    # tồn đầu kỳ = tồn cuối của ngày liền trước `from` (21/10)
    assert r22["opening"] == _row(http, item, month="2026-10", to="2026-10-21")["closing"]


def test_to_cuts_off_later_rows(http: TestClient, db: Session) -> None:
    item = _first_item(db)
    before = _row(http, item, month="2026-10", to="2026-10-19")
    _insert(db, item, "IN", 3, "2026-10-20 10:00+07")
    assert _row(http, item, month="2026-10", to="2026-10-19") == before


def test_single_day_range(http: TestClient, db: Session) -> None:
    item = _first_item(db)
    day = {"month": "2026-10", "from": "2026-10-20", "to": "2026-10-20"}
    before = _row(http, item, **day)
    _insert(db, item, "IN", 6, "2026-10-20 10:00+07")
    after = _row(http, item, **day)
    assert after["inbound"] == before["inbound"] + 6 and after["opening"] == before["opening"]


def test_other_is_exactly_the_transfer_and_produce_rows(http: TestClient, db: Session) -> None:
    """`other` là phần dư trong code, nên đối chiếu với tổng PRODUCE/TRANSFER tính độc lập từ sổ."""
    item = _first_item(db)
    _insert(db, item, "PRODUCE", 6, "2026-10-20 10:00+07")
    expected = {
        r[0]: float(r[1])
        for r in db.execute(
            text("""
                SELECT l.item_id, sum(l.delta_base) FROM inventory_log l
                WHERE l.tenant_id = 1 AND l.location_id = :loc AND l.action IN ('PRODUCE', 'TRANSFER')
                  AND l.reverses_id IS NULL
                  AND NOT EXISTS (SELECT 1 FROM inventory_log r WHERE r.reverses_id = l.id)
                  AND (l.event_time AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
                      BETWEEN '2026-10-01' AND '2026-10-31'
                GROUP BY 1
            """),
            {"loc": WAREHOUSE},
        )
    }
    assert expected[item] >= 6.0
    for r in _all_rows(http, **OCT):
        assert r["other"] == pytest.approx(expected.get(r["itemId"], 0.0)), r["name"]
    assert _row(http, item, **OCT)["variance"] == 0.0


def test_waste_column(http: TestClient, db: Session) -> None:
    item = _first_item(db)
    before = _row(http, item, **OCT)
    _insert(db, item, "WASTE", -2, "2026-10-20 10:00+07")
    after = _row(http, item, **OCT)
    assert after["waste"] == before["waste"] + 2 and after["closing"] == before["closing"] - 2


def test_status_filters_partition_the_table(http: TestClient) -> None:
    total = _get(http, "/api/stock", pageSize=1, **OCT)["total"]
    in_stock = _all_rows(http, status="in_stock", **OCT)
    out_of_stock = _all_rows(http, status="out_of_stock", **OCT)
    assert len(in_stock) + len(out_of_stock) == total
    assert all(r["closing"] > 0 for r in in_stock) and all(r["closing"] <= 0 for r in out_of_stock)


def test_only_moved_drops_untouched_items(http: TestClient) -> None:
    all_rows = {r["itemId"]: r for r in _all_rows(http, **OCT)}
    moved = {r["itemId"] for r in _all_rows(http, onlyMoved="true", **OCT)}
    assert 0 < len(moved) < len(all_rows)
    for item_id in set(all_rows) - moved:
        r = all_rows[item_id]
        assert r["inbound"] == r["outboundTotal"] == r["waste"] == r["variance"] == 0


def test_search_is_case_insensitive_and_matches_name(http: TestClient) -> None:
    lower = {r["itemId"] for r in _all_rows(http, q="cà phê", **OCT)}
    upper = {r["itemId"] for r in _all_rows(http, q="CÀ PHÊ", **OCT)}
    assert lower == upper and len(lower) > 0
    assert all("cà phê" in r["name"].lower() for r in _all_rows(http, q="cà phê", **OCT))


def test_search_also_matches_code_when_loaded(http: TestClient, db: Session) -> None:
    item = _first_item(db)
    db.execute(text("UPDATE items SET code = 'ZZ-TEST-9' WHERE id = :i"), {"i": item})
    rows = _all_rows(http, q="zz-test", **OCT)
    assert [(r["itemId"], r["code"]) for r in rows] == [(item, "ZZ-TEST-9")]


@pytest.mark.parametrize("q", ["%", "_", "\\"])
def test_search_treats_wildcards_literally(http: TestClient, q: str) -> None:
    assert _get(http, "/api/stock", q=q, **OCT)["total"] == 0


def test_category_filter_accepts_several_values(http: TestClient) -> None:
    one = _get(http, "/api/stock", pageSize=1, category="MERCHANDISE", **OCT)["total"]
    two = _get(http, "/api/stock", pageSize=1, category=["MERCHANDISE", "HÀNG SẢN XUẤT"], **OCT)["total"]
    assert 0 < one < two < 109
    rows = _all_rows(http, category=["MERCHANDISE", "HÀNG SẢN XUẤT"], **OCT)
    assert {r["category"] for r in rows} == {"MERCHANDISE", "HÀNG SẢN XUẤT"}


@pytest.mark.parametrize("key", ["name", "code", "category", "closing", "variance"])
@pytest.mark.parametrize("order", ["asc", "desc"])
def test_every_sort_key_works(http: TestClient, key: str, order: str) -> None:
    rows = _all_rows(http, sort=key, order=order, **OCT)
    assert len(rows) == 109
    if key == "closing":
        values = [r["closing"] for r in rows]
        assert values == sorted(values, reverse=order == "desc")


def test_default_sort_is_name_ascending(http: TestClient, db: Session) -> None:
    got = [r["itemId"] for r in _all_rows(http, **OCT)]
    expected = [
        r[0]
        for r in db.execute(
            text("SELECT id FROM items WHERE id = ANY(CAST(:ids AS bigint[])) ORDER BY lower(name), id"),
            {"ids": got},
        )
    ]
    assert got == expected  # cùng collation với DB (tiếng Việt), không so bằng sorted() của Python


def test_pagination_walks_every_item_once(http: TestClient) -> None:
    seen: list[int] = []
    for page in (1, 2, 3):
        body = _get(http, "/api/stock", page=page, pageSize=50, **OCT)
        assert body["total"] == 109 and body["page"] == page
        seen += [r["itemId"] for r in body["items"]]
    assert len(seen) == 109 and len(set(seen)) == 109


def test_page_beyond_the_end_is_empty_not_an_error(http: TestClient) -> None:
    body = _get(http, "/api/stock", page=99, pageSize=50, **OCT)
    assert body["items"] == [] and body["total"] == 109  # tổng thật để pager còn đường quay về
    assert _get(http, "/api/stock", page=99, q="zzz-khong-co", **OCT)["total"] == 0


@pytest.mark.parametrize(
    "params",
    [
        {"pageSize": 201},
        {"pageSize": 0},
        {"page": 0},
        {"page": 100_001},
        {"status": "weird"},
        {"sort": "price"},
        {"order": "up"},
        {"month": "bad"},
        {"onlyMoved": "maybe"},
    ],
)
def test_invalid_params_are_422(http: TestClient, params: dict[str, object]) -> None:
    assert http.get("/api/stock", params=params).status_code == 422


def test_only_the_warehouse_is_read(http: TestClient, db: Session) -> None:
    """Dòng sổ của chi nhánh không được lẫn vào số liệu kho tổng."""
    item = _first_item(db)
    before = _row(http, item, **OCT)
    admin = db.execute(text("SELECT id FROM admins ORDER BY id LIMIT 1")).scalar_one()
    db.execute(
        text("""
            INSERT INTO inventory_log (tenant_id, location_id, item_id, action, qty, unit, qty_base,
                                       delta_base, event_time, admin_id, parser_source)
            VALUES (1, 2, :item, 'IN', 50, 'x', 50, 50,
                    CAST('2026-10-20 10:00+07' AS timestamptz), :a, 'manual')
        """),
        {"item": item, "a": admin},
    )
    assert _row(http, item, **OCT) == before
