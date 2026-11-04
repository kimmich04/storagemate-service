"""Fixture dùng chung: client async gọi thẳng vào app (httpx + ASGITransport), không cần chạy server."""

import re
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

FIXTURES_DIR = Path(__file__).parent / "fixtures"
MESSAGE_START = re.compile(r"^\d+\.\s", flags=re.MULTILINE)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture(scope="session")
def real_messages() -> list[str]:
    """118 phiếu thật của Kho tổng (gitignored) — thiếu file thì bỏ qua test thay vì fail."""
    path = FIXTURES_DIR / "tin_nhan_118.txt"
    if not path.exists():
        pytest.skip("thiếu tests/fixtures/tin_nhan_118.txt (dữ liệu thật, không commit)")
    return MESSAGE_START.split(path.read_text(encoding="utf-8"))[1:]
