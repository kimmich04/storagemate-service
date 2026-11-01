import pytest


@pytest.mark.anyio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_openapi_has_api_prefix(client):
    resp = await client.get("/api/openapi.json")
    assert resp.status_code == 200
