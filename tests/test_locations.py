"""GET /api/locations + phạm vi kho (DashboardScope). Cần PostgreSQL thật đã migrate và nạp dữ liệu kho."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.models import Admin
from app.config import settings
from app.dashboard.dependencies import Scope
from app.main import app


@pytest.fixture
def dev_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DEV_AUTH_ENABLED", True)


@pytest.fixture
def http() -> TestClient:
    return TestClient(app)


def test_locations_returns_only_branches(http: TestClient, dev_auth: None) -> None:
    res = http.get("/api/locations")
    assert res.status_code == 200
    body = res.json()
    assert body
    assert {"id", "code", "name"} == set(body[0])
    assert all(b["code"] not in ("KT_SG", "DOI_TAC") for b in body)


def test_locations_needs_auth_when_dev_auth_off(http: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # đặt cờ rõ ràng: không dựa vào giá trị mặc định, vì .env của máy dev có thể đã bật DEV_AUTH_ENABLED
    monkeypatch.setattr(settings, "DEV_AUTH_ENABLED", False)
    assert http.get("/api/locations").status_code == 501


# --- phạm vi kho: gắn một route thử vào app riêng để kiểm DashboardScope ---
scope_app = FastAPI()


@scope_app.get("/scope")
def show_scope(scope: Scope) -> dict[str, object]:
    return {"id": scope.location.id, "kind": scope.location.kind, "tz": scope.timezone}


@pytest.fixture
def scope_http(dev_auth: None) -> TestClient:
    from app.exceptions import register_exception_handlers

    register_exception_handlers(scope_app)
    return TestClient(scope_app)


def test_scope_defaults_to_warehouse(scope_http: TestClient) -> None:
    body = scope_http.get("/scope").json()
    assert body["kind"] == "warehouse"
    assert body["tz"] == "Asia/Ho_Chi_Minh"


def test_scope_accepts_branch(scope_http: TestClient) -> None:
    branches = TestClient(app).get("/api/locations").json()
    res = scope_http.get("/scope", params={"location_id": branches[0]["id"]})
    assert res.status_code == 200 and res.json()["kind"] == "branch"


@pytest.mark.parametrize("bad_id", [1, 4, 99999])  # kho tổng, đối tác, không tồn tại
def test_scope_rejects_non_branch(scope_http: TestClient, bad_id: int) -> None:
    assert scope_http.get("/scope", params={"location_id": bad_id}).status_code == 404


def test_locked_admin_cannot_view_other_location(scope_http: TestClient) -> None:
    from app.auth import dependencies

    locked = Admin(id=1, tenant_id=1, email="x", name="x", password_hash="x", location_id=2)
    scope_app.dependency_overrides[dependencies.get_dev_admin] = lambda: locked
    try:
        assert scope_http.get("/scope", params={"location_id": 3}).status_code == 403
        assert scope_http.get("/scope", params={"location_id": 2}).status_code == 200
        assert scope_http.get("/scope").json()["id"] == 2  # bỏ trống → kho của chính admin
    finally:
        scope_app.dependency_overrides.clear()
