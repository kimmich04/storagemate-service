"""Bảng admins — Phase 1 chỉ dùng làm người ghi cho tồn đầu kỳ / dữ liệu ảo (import_opening.py)."""

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base
from app.staff import models as _staff  # noqa: F401 — nạp bảng đích của ForeignKey


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    email: Mapped[str]
    name: Mapped[str]
    password_hash: Mapped[str]
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
