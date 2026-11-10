"""Kết nối PostgreSQL bằng SQLAlchemy 2.0 (sync, driver psycopg 3).

Route dùng get_db nên khai báo `def` (không `async def`): FastAPI tự chạy trong threadpool,
không chặn event loop.
"""

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Dependency: mỗi request một session, tự đóng khi xong."""
    with SessionLocal() as session:
        yield session


DbSession = Annotated[Session, Depends(get_db)]
