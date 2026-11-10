"""GET /api/dashboard/in-out — chạy trên PostgreSQL thật có dữ liệu demo tháng 10/2026."""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


@pytest.fixture
def http(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "DEV_AUTH_ENABLED", True)
    return TestClient(app)


def _get(http: TestClient, **params: object) -> dict:
    res = http.get("/api/dashboard/in-out", params=params)
    assert res.status_code == 200, res.text
    return res.json()


@pytest.mark.parametrize("n", [7, 14, 30])
def test_returns_exactly_range_days(http: TestClient, n: int) -> None:
    body = _get(http, range=n, to="2026-10-31")
    assert len(body["days"]) == n
    assert body["to"] == "2026-10-31"
    assert body["from"] == body["days"][0]["date"]
    assert set(body["days"][0]) == {"date", "inCount", "outCount"}


def test_warehouse_week_matches_known_counts(http: TestClient) -> None:
    days = _get(http, range=7, to="2026-10-31")["days"]
    assert sum(d["inCount"] for d in days) == 6
    assert sum(d["outCount"] for d in days) == 44


def test_balancing_rows_are_not_counted(http: TestClient) -> None:
    days = _get(http, range=7, to="2026-10-31", location_id=2)["days"]
    assert sum(d["inCount"] for d in days) == 100
    assert sum(d["outCount"] for d in days) == 0  # 121 dòng "Thực xuất T10" bị loại


def test_default_end_is_latest_ledger_day(http: TestClient) -> None:
    assert _get(http, range=7)["to"] == "2026-10-31"


def test_branch_without_ledger_returns_zeros(http: TestClient) -> None:
    days = _get(http, range=7, location_id=3)["days"]
    assert len(days) == 7 and all(d["inCount"] == d["outCount"] == 0 for d in days)


@pytest.mark.parametrize("params", [{"range": 5}, {"location_id": 1}, {"location_id": 999}])
def test_bad_params(http: TestClient, params: dict) -> None:
    res = http.get("/api/dashboard/in-out", params=params)
    assert res.status_code in (404, 422)


def _kpi(http: TestClient, which: str, **params: object) -> dict:
    res = http.get(f"/api/dashboard/kpis/{which}", params=params)
    assert res.status_code == 200, res.text
    return res.json()


@pytest.mark.parametrize("loc", [None, 2, 3])
def test_kpis_match_in_out_chart(http: TestClient, loc: int | None) -> None:
    """Ô KPI 7 ngày phải khớp biểu đồ: kỳ này = 7 ngày cuối, kỳ trước = 7 ngày liền trước (range=14)."""
    extra = {} if loc is None else {"location_id": loc}
    days = _get(http, range=14, to="2026-10-31", **extra)["days"]
    prev, cur = days[:7], days[7:]
    for which, key in (("stock-in", "inCount"), ("stock-out", "outCount")):
        c, p = sum(d[key] for d in cur), sum(d[key] for d in prev)
        expected = 0 if p == 0 else round((c - p) / p * 100)
        assert _kpi(http, which, range=7, to="2026-10-31", **extra) == {"value": c, "deltaPct": expected}


def test_kpis_known_week(http: TestClient) -> None:
    assert _kpi(http, "stock-in", range=7, to="2026-10-31")["value"] == 6
    assert _kpi(http, "stock-out", range=7, to="2026-10-31")["value"] == 44


def test_kpis_zero_previous_gives_zero_delta(http: TestClient) -> None:
    assert _kpi(http, "stock-in", range=7, location_id=3) == {"value": 0, "deltaPct": 0}


# ----- recent-transactions -----
def _recent(http: TestClient, **params: object) -> list[dict]:
    res = http.get("/api/dashboard/recent-transactions", params=params)
    assert res.status_code == 200, res.text
    return res.json()["items"]


def test_recent_default_limit_and_fields(http: TestClient) -> None:
    items = _recent(http)
    assert len(items) == 10
    assert set(items[0]) == {
        "id", "at", "action", "isReversal", "qty", "unit", "itemName", "staffName",
        "locationName", "counterpart", "source", "confirmed",
    }  # fmt: skip
    assert isinstance(items[0]["qty"], int | float)
    assert items[0]["at"].endswith("+07:00")


@pytest.mark.parametrize("loc", [None, 2])
def test_recent_sorted_and_excludes_opening_and_balancing(http: TestClient, loc: int | None) -> None:
    extra = {} if loc is None else {"location_id": loc}
    items = _recent(http, limit=50, **extra)
    assert [i["at"] for i in items] == sorted((i["at"] for i in items), reverse=True)
    assert all(i["source"] != "opening" for i in items)
    # 121 dòng OUT "Thực xuất T10" (31/10 23:00) bị loại; 2 dòng ADJUST kiểm kê cùng giờ là thật nên vẫn hiện
    assert not any(i["at"].startswith("2026-10-31T23:00") and i["action"] == "OUT" for i in items)


def test_recent_warehouse_shows_counterpart(http: TestClient) -> None:
    assert any(i["counterpart"] for i in _recent(http, limit=50))


def test_recent_empty_branch_and_bad_params(http: TestClient) -> None:
    assert _recent(http, location_id=3) == []
    for params in ({"limit": 0}, {"limit": 51}):
        assert http.get("/api/dashboard/recent-transactions", params=params).status_code == 422
