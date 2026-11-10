"""Trang Nhập Kho: GET /api/transactions?type=IN [API-I2] và /api/transactions/in/daily [API-I1].

Chạy trên PostgreSQL thật (dữ liệu demo tháng 10/2026, kho tổng id=1). "Hôm nay" vá cố định = 09/11/2026.
Test cần thêm dòng sổ thì chèn trong transaction rollback của fixture `db`.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

TODAY = date(2026, 11, 9)
OCT = {"month": "2026-10"}
WAREHOUSE = 1


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.inventory.period.today_in", lambda tz: TODAY)


def _get(http: TestClient, url: str, **params: object) -> dict:
    res = http.get(url, params=params)
    assert res.status_code == 200, res.text
    return res.json()


def _list(http: TestClient, **params: object) -> dict:
    return _get(http, "/api/transactions", type="IN", **params)


def _daily(http: TestClient, **params: object) -> dict:
    return _get(http, "/api/transactions/in/daily", **params)


def _item(db: Session) -> int:
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
    source: str = "manual",
    reverses: int | None = None,
    note: str | None = None,
) -> int:
    admin = db.execute(text("SELECT id FROM admins ORDER BY id LIMIT 1")).scalar_one()
    return db.execute(
        text("""
            INSERT INTO inventory_log (tenant_id, location_id, item_id, action, qty, unit, qty_base,
                                       delta_base, event_time, admin_id, parser_source, reverses_id, note)
            VALUES (1, :loc, :item, CAST(:action AS inv_action), :qty, 'x', :qty, :delta,
                    CAST(:at AS timestamptz), :admin, CAST(:src AS parser_source), :rev, :note)
            RETURNING id
        """),
        {
            "loc": WAREHOUSE,
            "item": item,
            "action": action,
            "qty": abs(delta),
            "delta": delta,
            "at": at,
            "admin": admin,
            "src": source,
            "rev": reverses,
            "note": note,
        },
    ).scalar_one()


def _raw_in_count(db: Session, start: str, end: str) -> int:
    """Đếm độc lập: dòng IN không hủy, không bị hủy, trong [start, end] theo giờ VN."""
    return db.execute(
        text("""
            SELECT count(*) FROM inventory_log l
            WHERE l.tenant_id = 1 AND l.location_id = :loc AND l.action = 'IN'
              AND l.reverses_id IS NULL
              AND NOT EXISTS (SELECT 1 FROM inventory_log r WHERE r.reverses_id = l.id)
              AND coalesce(l.note, '') NOT LIKE 'Thực xuất T10%'
              AND (l.event_time AT TIME ZONE 'Asia/Ho_Chi_Minh')::date BETWEEN :s AND :e
        """),
        {"loc": WAREHOUSE, "s": start, "e": end},
    ).scalar_one()


# ---------- I2: danh sách ----------


def test_list_total_matches_raw_count(http: TestClient, db: Session) -> None:
    data = _list(http, **OCT)
    assert data["total"] == _raw_in_count(db, "2026-10-01", "2026-10-31") > 0
    assert data["period"] == {"month": "2026-10", "from": "2026-10-01", "to": "2026-10-31"}
    assert data["page"] == 1
    assert data["pageSize"] == 50


def test_list_item_shape_and_order(http: TestClient) -> None:
    items = _list(http, **OCT)["items"]
    first = items[0]
    assert set(first) == {"id", "itemId", "code", "name", "unit", "qty", "eventDate"}
    assert isinstance(first["qty"], int | float)
    keys = [(i["eventDate"], i["id"]) for i in items]
    assert keys == sorted(keys, reverse=True)


def test_pagination_covers_all_rows_without_overlap(http: TestClient) -> None:
    total = _list(http, **OCT)["total"]
    seen: list[int] = []
    page = 1
    while True:
        data = _list(http, page=page, pageSize=30, **OCT)
        seen += [i["id"] for i in data["items"]]
        if len(data["items"]) < 30:
            break
        page += 1
    assert len(seen) == total
    assert len(set(seen)) == total


def test_page_beyond_end_is_empty_but_keeps_the_real_total(http: TestClient) -> None:
    real = _list(http, **OCT)["total"]
    assert real > 0
    data = _list(http, page=999, **OCT)
    assert data["items"] == []
    assert data["total"] == real  # để pager còn đường quay về trang đầu
    assert _list(http, page=999, q="zzz-khong-co", **OCT)["total"] == 0


def test_empty_period_returns_200_empty(http: TestClient) -> None:
    data = _list(http)  # tháng 11/2026 chưa có giao dịch
    assert data["total"] == 0
    assert data["items"] == []


def test_date_range_filters_rows(http: TestClient, db: Session) -> None:
    data = _list(http, month="2026-10", **{"from": "2026-10-10", "to": "2026-10-12"})
    assert data["total"] == _raw_in_count(db, "2026-10-10", "2026-10-12")
    assert all("2026-10-10" <= i["eventDate"] <= "2026-10-12" for i in data["items"])


def test_search_by_name_is_case_insensitive_and_needs_diacritics(http: TestClient) -> None:
    name = _list(http, **OCT)["items"][0]["name"]
    hit = _list(http, q=name.upper(), **OCT)
    assert hit["total"] >= 1
    assert all(name.lower() in i["name"].lower() for i in hit["items"])
    assert _list(http, q="zzz-khong-co", **OCT)["total"] == 0


def test_search_escapes_like_wildcards(http: TestClient) -> None:
    assert _list(http, q="%", **OCT)["total"] == 0
    assert _list(http, q="_", **OCT)["total"] == 0


def test_blank_search_is_ignored(http: TestClient) -> None:
    assert _list(http, q="   ", **OCT)["total"] == _list(http, **OCT)["total"]


def test_cancelled_pair_is_not_listed_or_counted(http: TestClient, db: Session) -> None:
    item = _item(db)
    before = _list(http, **OCT)["total"]
    original = _insert(db, item, "IN", 7, "2026-10-15 10:00+07")
    assert _list(http, **OCT)["total"] == before + 1
    _insert(db, item, "OUT", -7, "2026-10-15 10:05+07", source="undo", reverses=original)
    assert _list(http, **OCT)["total"] == before


def test_cancel_in_a_later_month_removes_original_from_its_month(http: TestClient, db: Session) -> None:
    item = _item(db)
    before = _list(http, **OCT)["total"]
    original = _insert(db, item, "IN", 7, "2026-10-15 10:00+07")
    _insert(db, item, "OUT", -7, "2026-11-02 10:00+07", source="undo", reverses=original)
    assert _list(http, **OCT)["total"] == before
    assert _list(http)["total"] == 0


def test_only_in_rows_are_listed(http: TestClient, db: Session) -> None:
    item = _item(db)
    before = _list(http, **OCT)["total"]
    _insert(db, item, "OUT", -3, "2026-10-15 10:00+07")
    _insert(db, item, "ADJUST", 3, "2026-10-15 10:00+07")
    assert _list(http, **OCT)["total"] == before


def test_balancing_note_rows_are_skipped(http: TestClient, db: Session) -> None:
    item = _item(db)
    before = _list(http, **OCT)["total"]
    _insert(db, item, "IN", 5, "2026-10-15 10:00+07", note="Thực xuất T10 cân bằng")
    assert _list(http, **OCT)["total"] == before


def test_timezone_boundary_uses_tenant_day(http: TestClient, db: Session) -> None:
    item = _item(db)
    # 31/10 23:30 giờ VN = 31/10 16:30 UTC; 01/11 00:30 giờ VN = 31/10 17:30 UTC
    late = _insert(db, item, "IN", 4, "2026-10-31 23:30+07")
    early = _insert(db, item, "IN", 4, "2026-11-01 00:30+07")
    oct_ids = {i["id"] for i in _list(http, pageSize=200, page=1, **OCT)["items"]}
    nov_ids = {i["id"] for i in _list(http, pageSize=200)["items"]}
    assert late in oct_ids and late not in nov_ids
    assert early in nov_ids and early not in oct_ids


def test_unit_is_the_logged_unit_not_base_unit(http: TestClient, db: Session) -> None:
    item = _item(db)
    row_id = _insert(db, item, "IN", 9, "2026-10-31 11:00+07")
    row = next(i for i in _list(http, pageSize=200, **OCT)["items"] if i["id"] == row_id)
    assert row["unit"] == "x"
    assert row["qty"] == 9


# ---------- I2: tham số sai ----------


@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"type": "XYZ"}, 422),
        ({}, 422),  # thiếu type
        ({"type": "IN", "pageSize": 201}, 422),
        ({"type": "IN", "pageSize": 0}, 422),
        ({"type": "IN", "page": 0}, 422),
        ({"type": "IN", "page": 100_001}, 422),
        ({"type": "IN", "month": "2026-13"}, 422),
        ({"type": "IN", "month": "2026-07"}, 422),  # trước tháng đầu
        ({"type": "IN", "month": "2026-12"}, 422),  # tương lai
        ({"type": "IN", "month": "2026-10", "to": "2026-11-01"}, 422),  # ngoài tháng
        ({"type": "IN", "month": "2026-11", "to": "2026-11-10"}, 422),  # quá hôm nay
        ({"type": "IN", "month": "2026-10", "from": "2026-10-20", "to": "2026-10-10"}, 422),
    ],
)
def test_list_rejects_bad_params(http: TestClient, params: dict, code: int) -> None:
    assert http.get("/api/transactions", params=params).status_code == code


def test_invalid_period_body(http: TestClient) -> None:
    body = http.get("/api/transactions", params={"type": "IN", "month": "2026-12"}).json()
    assert body["code"] == "invalid_period"


# ---------- I1: theo ngày ----------


def test_daily_covers_every_day_and_sums_to_list_total(http: TestClient) -> None:
    daily = _daily(http, **OCT)
    days = daily["days"]
    assert len(days) == 31
    assert days[0]["date"] == "2026-10-01" and days[-1]["date"] == "2026-10-31"
    assert sum(d["count"] for d in days) == _list(http, **OCT)["total"]
    assert daily["period"] == {"month": "2026-10", "from": "2026-10-01", "to": "2026-10-31"}


def test_daily_subrange_matches_list(http: TestClient) -> None:
    params = {"month": "2026-10", "from": "2026-10-10", "to": "2026-10-14"}
    daily = _daily(http, **params)
    assert [d["date"] for d in daily["days"]] == [f"2026-10-{n}" for n in range(10, 15)]
    assert sum(d["count"] for d in daily["days"]) == _list(http, **params)["total"]


def test_daily_empty_month_is_all_zero_up_to_today(http: TestClient) -> None:
    days = _daily(http)["days"]  # tháng 11: 01..09
    assert len(days) == 9
    assert all(d["count"] == 0 for d in days)


def test_daily_ignores_cancelled_pair(http: TestClient, db: Session) -> None:
    item = _item(db)
    day = {"month": "2026-10", "from": "2026-10-15", "to": "2026-10-15"}
    before = _daily(http, **day)["days"][0]["count"]
    original = _insert(db, item, "IN", 7, "2026-10-15 10:00+07")
    assert _daily(http, **day)["days"][0]["count"] == before + 1
    _insert(db, item, "OUT", -7, "2026-10-15 10:05+07", source="undo", reverses=original)
    assert _daily(http, **day)["days"][0]["count"] == before


def test_daily_timezone_boundary(http: TestClient, db: Session) -> None:
    item = _item(db)
    day31 = {"month": "2026-10", "from": "2026-10-31", "to": "2026-10-31"}
    before = _daily(http, **day31)["days"][0]["count"]
    _insert(db, item, "IN", 4, "2026-10-31 23:30+07")
    _insert(db, item, "IN", 4, "2026-11-01 00:30+07")
    assert _daily(http, **day31)["days"][0]["count"] == before + 1


@pytest.mark.parametrize(
    "params",
    [{"month": "2026-12"}, {"month": "bad"}, {"month": "2026-10", "to": "2026-11-01"}],
)
def test_daily_rejects_bad_period(http: TestClient, params: dict) -> None:
    assert http.get("/api/transactions/in/daily", params=params).status_code == 422
