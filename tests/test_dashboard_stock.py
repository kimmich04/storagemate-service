"""low-stock, below-min, tracked-items, stock history. Dữ liệu demo có min_qty = 0 hết, nên test gán tạm
min_qty trong transaction rollback (fixture `db`/`http` ở conftest.py) → DB không bị đổi."""

import unicodedata

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

MIN = 10  # mức tối thiểu gán tạm cho mọi mặt hàng


def _set_min(db: Session, value: int) -> None:
    db.execute(text("UPDATE items SET min_qty = :v WHERE tenant_id = 1"), {"v": value})


def _expected_below(db: Session, loc: int) -> int:
    return db.execute(
        text("SELECT count(*) FROM current_stock WHERE tenant_id = 1 AND location_id = :l AND qty_base < :m"),
        {"l": loc, "m": MIN},
    ).scalar_one()


def test_no_min_set_gives_empty(http: TestClient, db: Session) -> None:
    assert http.get("/api/dashboard/kpis/below-min").json() == {"count": 0}
    assert http.get("/api/dashboard/low-stock").json() == {"items": []}


@pytest.mark.parametrize("loc", [None, 2])
def test_below_min_count(http: TestClient, db: Session, loc: int | None) -> None:
    _set_min(db, MIN)
    params = {} if loc is None else {"location_id": loc}
    body = http.get("/api/dashboard/kpis/below-min", params=params).json()
    assert body == {"count": _expected_below(db, loc or 1)}
    assert body["count"] > 0


def test_low_stock_sorted_by_ratio(http: TestClient, db: Session) -> None:
    _set_min(db, MIN)
    items = http.get("/api/dashboard/low-stock").json()["items"]
    assert len(items) == 5
    assert set(items[0]) == {"itemId", "name", "unit", "qty", "minQty", "avgDailyOut"}
    ratios = [i["qty"] / i["minQty"] for i in items]
    assert ratios == sorted(ratios)
    assert all(i["minQty"] == MIN and isinstance(i["qty"], float) for i in items)


def test_avg_daily_out_is_30_day_out_sum_divided_by_30(http: TestClient, db: Session) -> None:
    _set_min(db, 100000)  # mọi mặt hàng đều "dưới mức" → lấy được nhiều dòng
    items = http.get("/api/dashboard/low-stock", params={"limit": 20}).json()["items"]
    for it in items:
        out_sum = db.execute(
            text("""
                SELECT coalesce(sum(qty_base), 0) FROM inventory_log
                WHERE tenant_id = 1 AND location_id = 1 AND item_id = :i AND action = 'OUT'
                  AND (event_time AT TIME ZONE 'Asia/Ho_Chi_Minh')::date BETWEEN '2026-10-02' AND '2026-10-31'
            """),
            {"i": it["itemId"]},
        ).scalar_one()
        assert it["avgDailyOut"] == pytest.approx(float(out_sum) / 30, abs=0.001)


def test_empty_branch_and_bad_limit(http: TestClient, db: Session) -> None:
    _set_min(db, MIN)
    assert http.get("/api/dashboard/low-stock", params={"location_id": 3}).json() == {"items": []}
    assert http.get("/api/dashboard/kpis/below-min", params={"location_id": 3}).json() == {"count": 0}
    for limit in (0, 21):
        assert http.get("/api/dashboard/low-stock", params={"limit": limit}).status_code == 422


# ----- tracked-items -----
def _plain(name: str) -> str:
    """Bỏ dấu tiếng Việt để so thứ tự từ điển."""
    stripped = unicodedata.normalize("NFD", name.lower().replace("đ", "d"))
    return "".join(c for c in stripped if not unicodedata.combining(c))


def _items(http: TestClient, **params: object) -> list[dict]:
    res = http.get("/api/dashboard/tracked-items", params=params)
    assert res.status_code == 200, res.text
    return res.json()["items"]


@pytest.mark.parametrize(("loc", "expected"), [(None, 109), (2, 211)])
def test_tracked_items_lists_all_items_of_location(http: TestClient, loc: int | None, expected: int) -> None:
    items = _items(http, **({} if loc is None else {"location_id": loc}))
    assert len(items) == expected
    assert set(items[0]) == {"id", "name", "unit", "tracked"}
    keys = [_plain(i["name"]) for i in items]
    assert keys == sorted(keys)  # A–Z theo từ điển có dấu (Áo đứng cạnh ao, không đứng sau z)
    assert not any(i["tracked"] for i in items)  # dữ liệu hiện chưa ghim món nào


def test_tracked_filter_follows_pinned(http: TestClient, db: Session) -> None:
    assert _items(http, tracked="true") == []
    db.execute(
        text(
            "UPDATE items SET pinned = true WHERE id IN "
            "(SELECT item_id FROM current_stock WHERE location_id = 1 LIMIT 3)"
        )
    )
    on, off = _items(http, tracked="true"), _items(http, tracked="false")
    assert len(on) == 3 and all(i["tracked"] for i in on)
    assert len(off) == 106 and not any(i["tracked"] for i in off)
    assert len(_items(http)) == 109


def test_tracked_items_empty_branch(http: TestClient) -> None:
    assert _items(http, location_id=3) == []


# ----- stock/{item_id}/history -----
def _history(http: TestClient, item_id: int, **params: object):
    return http.get(f"/api/dashboard/stock/{item_id}/history", params=params)


def _items_of(db: Session, loc: int, limit: int = 5) -> list[int]:
    rows = db.execute(
        text("SELECT item_id FROM current_stock WHERE location_id = :l ORDER BY item_id LIMIT :n"),
        {"l": loc, "n": limit},
    )
    return [r[0] for r in rows]


@pytest.mark.parametrize("loc", [1, 2])
def test_history_last_point_equals_current_stock(http: TestClient, db: Session, loc: int) -> None:
    for item_id in _items_of(db, loc, 8):
        res = _history(http, item_id, location_id=loc) if loc == 2 else _history(http, item_id)
        body = res.json()
        assert res.status_code == 200 and len(body["points"]) == 30
        current = db.execute(
            text("SELECT qty_base FROM current_stock WHERE location_id = :l AND item_id = :i"),
            {"l": loc, "i": item_id},
        ).scalar_one()
        assert body["points"][-1] == {"date": "2026-10-31", "qty": float(current)}
        assert body["location"]["id"] == loc and body["item"]["id"] == item_id


def test_history_is_running_sum_of_delta(http: TestClient, db: Session) -> None:
    item_id = _items_of(db, 1, 1)[0]
    body = _history(http, item_id, days=7).json()
    for p in body["points"]:
        expected = db.execute(
            text("""
                SELECT coalesce(sum(delta_base), 0) FROM inventory_log
                WHERE tenant_id = 1 AND location_id = 1 AND item_id = :i
                  AND (event_time AT TIME ZONE 'Asia/Ho_Chi_Minh')::date <= :d
            """),
            {"i": item_id, "d": p["date"]},
        ).scalar_one()
        assert p["qty"] == float(expected)


def test_history_returns_min_qty(http: TestClient, db: Session) -> None:
    item_id = _items_of(db, 1, 1)[0]
    assert _history(http, item_id).json()["minQty"] == 0
    db.execute(text("UPDATE items SET min_qty = 7.5 WHERE id = :i"), {"i": item_id})
    assert _history(http, item_id).json()["minQty"] == 7.5


def test_history_not_found_cases(http: TestClient, db: Session) -> None:
    only_in_2 = db.execute(
        text(
            "SELECT item_id FROM current_stock WHERE location_id = 2 AND item_id NOT IN "
            "(SELECT item_id FROM current_stock WHERE location_id = 1) LIMIT 1"
        )
    ).scalar_one()
    assert _history(http, 999999).status_code == 404  # không tồn tại
    assert _history(http, only_in_2).status_code == 404  # có ở kho 2 nhưng không có ở kho tổng đang xem
    assert _history(http, only_in_2, location_id=2).status_code == 200
    assert _history(http, _items_of(db, 1, 1)[0], location_id=3).status_code == 404  # Phú Quốc chưa có sổ


@pytest.mark.parametrize("days", [0, 91])
def test_history_bad_days(http: TestClient, db: Session, days: int) -> None:
    assert _history(http, _items_of(db, 1, 1)[0], days=days).status_code == 422
