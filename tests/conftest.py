"""Fixture dùng chung: client async gọi thẳng vào app (httpx + ASGITransport), không cần chạy server."""

from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from app.config import settings
from app.database import engine, get_db
from app.main import app


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    """Session trên PostgreSQL thật; mọi thay đổi trong test bị rollback. Bật admin demo cho dashboard."""
    monkeypatch.setattr(settings, "DEV_AUTH_ENABLED", True)
    conn = engine.connect()
    outer = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()
        outer.rollback()
        conn.close()


@pytest.fixture
def http(db: Session) -> TestClient:
    return TestClient(app)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
