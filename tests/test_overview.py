"""Trang Tổng quan: /api/dashboard/* [API-T1..T6, T8] (T7 = [API-O3] của Xuất Kho, test ở test_outbound).

Chạy trên PostgreSQL thật (dữ liệu demo tháng 10/2026, kho tổng id=1). "Hôm nay" vá cố định = 09/11/2026.
Dòng thêm vào chỉ nằm trong transaction rollback của fixture `db`. Tháng 10 có 254 lượt xuất tới 3 nơi nhận.
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.dashboard.overview.service import delta_pct, previous_month_range
from app.inventory.period import resolve_period

TODAY = date(2026, 11, 9)
OCT = {"month": "2026-10"}
NOV = {"month": "2026-11"}  # tháng hiện tại: 1/11–9/11, chưa có giao dịch
WAREHOUSE = 1
BRANCH_220 = 2


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.inventory.period.today_in", lambda tz: TODAY)


def _get(http: TestClient, url: str, **params: object) -> dict:
    res = http.get(url, params=params)
    assert res.status_code == 200, res.text
    return res.json()


def _dash(http: TestClient, path: str, **params: object) -> dict:
    return _get(http, f"/api/dashboard/{path}", **params)


def _item(db: Session, nth: int = 0) -> int:
    return db.execute(
        text("SELECT item_id FROM current_stock WHERE location_id = :l ORDER BY item_id LIMIT 1 OFFSET :n"),
        {"l": WAREHOUSE, "n": nth},
    ).scalar_one()


def _insert(
    db: Session,
    item: int,
    action: str,
    delta: int | Decimal,
    at: str,
    dest: int | None = None,
    source: str = "manual",
    reverses: int | None = None,
) -> int:
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


# ---------- previous_month_range / delta_pct (thuần, không cần DB) ----------


def _period(today: date, month: str, from_: date | None = None, to: date | None = None):
    return resolve_period(today, month, from_, to)


def test_previous_range_same_day_numbers() -> None:
    p = _period(TODAY, "2026-11")  # 1/11–9/11
    assert previous_month_range(p) == (date(2026, 10, 1), date(2026, 10, 9))


def test_previous_range_full_past_month() -> None:
    p = _period(TODAY, "2026-10")  # 1/10–31/10
    assert previous_month_range(p) == (date(2026, 9, 1), date(2026, 9, 30))  # tháng 9 chỉ có 30 ngày


def test_previous_range_clips_to_short_month() -> None:
    p = _period(date(2027, 3, 31), "2027-03", date(2027, 3, 29), date(2027, 3, 31))
    assert previous_month_range(p) == (date(2027, 2, 28), date(2027, 2, 28))


def test_previous_range_crosses_year() -> None:
    p = _period(date(2027, 1, 20), "2027-01", date(2027, 1, 5), date(2027, 1, 10))
    assert previous_month_range(p) == (date(2026, 12, 5), date(2026, 12, 10))


@pytest.mark.parametrize(
    ("cur", "prev", "expected"), [(5, 0, None), (0, 0, None), (15, 10, 50), (5, 10, -50), (0, 10, -100)]
)
def test_delta_pct(cur: int, prev: int, expected: int | None) -> None:
    assert delta_pct(cur, prev) == expected


# ---------- T1..T4: bốn ô KPI khớp số của các trang con ----------


def test_stock_in_matches_inbound_total(http: TestClient) -> None:
    total = _get(http, "/api/transactions", type="IN", **OCT)["total"]
    assert total > 0
    assert _dash(http, "kpis/stock-in", **OCT)["value"] == total


def test_stock_out_matches_outbound_total(http: TestClient) -> None:
    assert _dash(http, "kpis/stock-out", **OCT)["value"] == 254
    assert _get(http, "/api/transactions/out/total", **OCT)["count"] == 254


def test_destinations_counts_places_with_exits(http: TestClient) -> None:
    assert _dash(http, "kpis/destinations", **OCT)["value"] == 3  # 220, Phú Quốc, đối tác


def test_items_in_is_distinct_items_not_rows(http: TestClient, db: Session) -> None:
    before = _dash(http, "kpis/items-in", **OCT)["value"]
    rows_before = _dash(http, "kpis/stock-in", **OCT)["value"]
    item = _item(db)
    _insert(db, item, "IN", 5, "2026-10-20 10:00+07")
    _insert(db, item, "IN", 5, "2026-10-21 10:00+07")
    assert _dash(http, "kpis/stock-in", **OCT)["value"] == rows_before + 2
    assert _dash(http, "kpis/items-in", **OCT)["value"] <= before + 1  # cùng mặt hàng chỉ đếm một lần


def test_unknown_destination_is_not_a_destination(http: TestClient, db: Session) -> None:
    _insert(db, _item(db), "OUT", -3, "2026-10-20 10:00+07", dest=None)
    assert _dash(http, "kpis/stock-out", **OCT)["value"] == 255
    assert _dash(http, "kpis/destinations", **OCT)["value"] == 3


def test_cancelled_pair_is_not_counted(http: TestClient, db: Session) -> None:
    before = _dash(http, "kpis/stock-in", **OCT)["value"]
    original = _insert(db, _item(db), "IN", 4, "2026-10-20 10:00+07")
    _insert(db, _item(db), "OUT", -4, "2026-10-20 10:05+07", source="undo", reverses=original)
    assert _dash(http, "kpis/stock-in", **OCT)["value"] == before


def test_kpi_respects_day_range(http: TestClient) -> None:
    sub = _dash(http, "kpis/stock-out", month="2026-10", **{"from": "2026-10-10", "to": "2026-10-12"})
    assert 0 < sub["value"] < 254


def test_kpi_empty_month_is_zero_and_delta_against_previous(http: TestClient) -> None:
    prev_in = _get(
        http, "/api/transactions", type="IN", month="2026-10", **{"from": "2026-10-01", "to": "2026-10-09"}
    )["total"]
    kpi = _dash(http, "kpis/stock-in", **NOV)  # 1/11–9/11 so với 1/10–9/10
    assert kpi["value"] == 0
    assert kpi["deltaPct"] == (None if prev_in == 0 else -100)


def test_kpi_delta_uses_same_day_numbers_of_previous_month(http: TestClient, db: Session) -> None:
    prev_in = _get(
        http, "/api/transactions", type="IN", month="2026-10", **{"from": "2026-10-01", "to": "2026-10-09"}
    )["total"]
    for day in (2, 3):
        _insert(db, _item(db), "IN", 1, f"2026-11-0{day} 10:00+07")
    kpi = _dash(http, "kpis/stock-in", **NOV)
    assert kpi["value"] == 2
    assert kpi["deltaPct"] == delta_pct(2, prev_in)


def test_kpi_delta_is_null_when_previous_month_empty(http: TestClient) -> None:
    # tháng 9 chưa có giao dịch → không so sánh được
    kpi = _dash(http, "kpis/stock-in", month="2026-10")
    assert kpi["value"] > 0
    assert kpi["deltaPct"] is None


# ---------- T5: ô "Còn tồn" (đầu kỳ → cuối kỳ) ----------


def test_in_stock_matches_stock_page_cards(http: TestClient) -> None:
    data = _dash(http, "kpis/in-stock", **OCT)
    assert data["closing"] == _get(http, "/api/stock/kpis/in-stock", **OCT)["count"]
    assert data["total"] == _get(http, "/api/stock/kpis/total-items", **OCT)["count"]
    assert 0 <= data["opening"] <= data["total"] and 0 <= data["closing"] <= data["total"]


def test_in_stock_opening_of_next_month_equals_closing_of_previous(http: TestClient) -> None:
    october = _dash(http, "kpis/in-stock", **OCT)
    november = _dash(http, "kpis/in-stock", **NOV)
    assert november["opening"] == october["closing"]
    assert november["closing"] == november["opening"]  # tháng 11 chưa có giao dịch


def test_in_stock_responds_to_stock_movement(http: TestClient, db: Session) -> None:
    item = db.execute(
        text(
            "SELECT item_id FROM current_stock "
            "WHERE location_id = :l AND qty_base > 0 ORDER BY item_id LIMIT 1"
        ),
        {"l": WAREHOUSE},
    ).scalar_one()
    qty = db.execute(
        text("SELECT qty_base FROM current_stock WHERE location_id = :l AND item_id = :i"),
        {"l": WAREHOUSE, "i": item},
    ).scalar_one()
    before = _dash(http, "kpis/in-stock", **NOV)
    _insert(db, item, "OUT", -qty, "2026-11-05 10:00+07", dest=BRANCH_220)  # xuất hết tồn
    after = _dash(http, "kpis/in-stock", **NOV)
    assert after["opening"] == before["opening"]
    assert after["closing"] == before["closing"] - 1


# ---------- T6: biểu đồ lượt nhập / xuất theo ngày ----------


def test_in_out_has_every_day_and_matches_kpis(http: TestClient) -> None:
    data = _dash(http, "in-out", **OCT)
    days = data["days"]
    assert data["period"] == {"month": "2026-10", "from": "2026-10-01", "to": "2026-10-31"}
    assert len(days) == 31
    assert set(days[0]) == {"date", "inCount", "outCount"}
    assert sum(d["inCount"] for d in days) == _dash(http, "kpis/stock-in", **OCT)["value"]
    assert sum(d["outCount"] for d in days) == _dash(http, "kpis/stock-out", **OCT)["value"] == 254


def test_in_out_empty_month_current_month_ends_today(http: TestClient) -> None:
    days = _dash(http, "in-out", **NOV)["days"]
    assert [d["date"] for d in days][0] == "2026-11-01"
    assert [d["date"] for d in days][-1] == "2026-11-09"
    assert all(d["inCount"] == d["outCount"] == 0 for d in days)


def test_in_out_day_range_and_timezone_boundary(http: TestClient, db: Session) -> None:
    # 23:30 giờ VN ngày 20/10 = 16:30 UTC cùng ngày; 00:30 VN ngày 21/10 = 17:30 UTC ngày 20/10
    _insert(db, _item(db), "IN", 1, "2026-10-20 23:30+07")
    _insert(db, _item(db), "IN", 1, "2026-10-21 00:30+07")
    base = {d["date"]: d["inCount"] for d in _dash(http, "in-out", **OCT)["days"]}
    sub = _dash(http, "in-out", month="2026-10", **{"from": "2026-10-20", "to": "2026-10-21"})["days"]
    assert [d["date"] for d in sub] == ["2026-10-20", "2026-10-21"]
    assert [d["inCount"] for d in sub] == [base["2026-10-20"], base["2026-10-21"]]
    assert base["2026-10-20"] >= 1 and base["2026-10-21"] >= 1


# ---------- T8: giao dịch gần đây ----------


def _recent(http: TestClient, **params: object) -> list[dict]:
    return _dash(http, "recent-transactions", **params)["items"]


def test_recent_default_limit_and_fields(http: TestClient) -> None:
    items = _recent(http)
    assert len(items) == 10
    assert set(items[0]) == {"id", "kind", "name", "unit", "qty", "eventDate", "destinationName"}
    assert isinstance(items[0]["qty"], int | float)


def test_recent_sorted_newest_first_and_mixes_kinds(http: TestClient) -> None:
    items = _recent(http, limit=50)
    assert [i["eventDate"] for i in items] == sorted((i["eventDate"] for i in items), reverse=True)
    assert {i["kind"] for i in items} == {"in", "out"}
    assert all((i["destinationName"] is not None) == (i["kind"] == "out") for i in items)


def test_recent_excludes_opening_balances_and_cancelled_pairs(http: TestClient, db: Session) -> None:
    original = _insert(db, _item(db), "IN", 4, "2026-10-31 20:00+07")
    _insert(db, _item(db), "OUT", -4, "2026-10-31 20:05+07", source="undo", reverses=original)
    ids = [i["id"] for i in _recent(http, limit=50)]
    assert original not in ids


def test_recent_shows_new_transaction_first(http: TestClient, db: Session) -> None:
    new_id = _insert(db, _item(db), "OUT", -2, "2026-11-08 09:00+07", dest=BRANCH_220)
    first = _recent(http)[0]
    assert first["id"] == new_id
    assert first["kind"] == "out"
    assert first["destinationName"] == "220 Lê Thánh Tôn"


# ---------- tham số sai ----------


@pytest.mark.parametrize(
    "path",
    ["kpis/stock-in", "kpis/items-in", "kpis/stock-out", "kpis/destinations", "kpis/in-stock", "in-out"],
)
def test_future_month_is_rejected(http: TestClient, path: str) -> None:
    res = http.get(f"/api/dashboard/{path}", params={"month": "2026-12"})
    assert res.status_code == 422
    assert res.json()["code"] == "invalid_period"


def test_bad_day_range_and_limit(http: TestClient) -> None:
    bad_range = http.get(
        "/api/dashboard/kpis/stock-in",
        params={"month": "2026-10", "from": "2026-10-20", "to": "2026-10-10"},
    )
    assert bad_range.status_code == 422
    assert http.get("/api/dashboard/kpis/stock-in", params={"month": "10/2026"}).status_code == 422
    for limit in (0, 51):
        assert http.get("/api/dashboard/recent-transactions", params={"limit": limit}).status_code == 422
