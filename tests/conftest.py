"""Fixture dùng chung: client async gọi thẳng vào app (httpx + ASGITransport), không cần chạy server."""

from collections.abc import AsyncIterator, Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from app.config import settings
from app.database import engine, get_db
import re
from pathlib import Path
from types import SimpleNamespace

from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine
from alembic import command
from app.auth.models import Admin
from app.items.models import Item
from app.items.service import db_names
from app.main import app
from app.parser.catalog import load_catalog
from app.staff.models import Location, Staff, Tenant

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = Path(__file__).parent / "fixtures"
MESSAGE_START = re.compile(r"^\d+\.\s", flags=re.MULTILINE)
# Giống seed T10: alias có dấu lẫn không dấu
TEST_LOCATIONS = [
    ("KT", "Kho tổng SG", "warehouse", ["kho tổng", "kho tong", "kt"]),
    ("K220", "220 Lê Thánh Tôn", "branch", ["220", "kho 220", "ltt"]),
    ("PQ", "Phú Quốc", "branch", ["pq", "phú quốc", "phu quoc"]),
    ("DT", "Đối tác / nội bộ", "partner", ["đối tác", "nội bộ"]),
]


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


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    """DB test riêng (TEST_DATABASE_URL), xoá sạch rồi migrate lại mỗi lần chạy pytest."""
    if not settings.TEST_DATABASE_URL:
        pytest.skip("thiếu TEST_DATABASE_URL (Postgres riêng cho test)")
    config = Config()  # không đọc alembic.ini: fileConfig ở env.py sẽ tắt logger của app (hỏng caplog)
    config.set_main_option("script_location", str(ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.TEST_DATABASE_URL.replace("%", "%%"))
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_engine(settings.TEST_DATABASE_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def db_connection(db_engine: Engine) -> Iterator[Connection]:
    """Một transaction ngoài cho cả test; commit trong code chỉ là SAVEPOINT → cuối test rollback hết."""
    with db_engine.connect() as connection:
        outer = connection.begin()
        yield connection
        outer.rollback()


@pytest.fixture
def session_factory(db_connection: Connection) -> Callable[[], Session]:
    return lambda: Session(bind=db_connection, join_transaction_mode="create_savepoint")


@pytest.fixture
def db_session(session_factory: Callable[[], Session]) -> Iterator[Session]:
    with session_factory() as session:
        yield session


@pytest.fixture
def seeded(db_session: Session) -> SimpleNamespace:
    """1 tenant, 4 kho, toàn bộ catalog vào items, 1 nhân viên kho tổng gắn chat-1. Chưa có tồn."""
    tenant = Tenant(name="Test")
    db_session.add(tenant)
    db_session.flush()
    locations = {
        code: Location(tenant_id=tenant.id, code=code, name=name, kind=kind, aliases=aliases)
        for code, name, kind, aliases in TEST_LOCATIONS
    }
    db_session.add_all(locations.values())
    db_session.flush()
    names = db_names(load_catalog())
    items = {
        entry.code: Item(
            tenant_id=tenant.id, code=entry.code, name=names[entry.code], base_unit=entry.base_unit
        )
        for entry in load_catalog()
    }
    db_session.add_all(items.values())
    admin = Admin(tenant_id=tenant.id, email="t@test", name="Test", password_hash="!")
    staff = Staff(
        tenant_id=tenant.id, default_location_id=locations["KT"].id, name="Lan", zalo_chat_id="chat-1"
    )
    db_session.add_all([admin, staff])
    db_session.flush()
    return SimpleNamespace(tenant=tenant, locations=locations, items=items, admin=admin, staff=staff)


@pytest.fixture(scope="session")
def real_messages() -> list[str]:
    """118 phiếu thật của Kho tổng (gitignored) — thiếu file thì bỏ qua test thay vì fail."""
    path = FIXTURES_DIR / "tin_nhan_118.txt"
    if not path.exists():
        pytest.skip("thiếu tests/fixtures/tin_nhan_118.txt (dữ liệu thật, không commit)")
    return MESSAGE_START.split(path.read_text(encoding="utf-8"))[1:]
