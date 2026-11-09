"""Bảng tenants và admins (khớp migration 0001_init). Tạo admin bằng scripts/create_admin.py."""

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(Text, default="Asia/Ho_Chi_Minh")
    archived_at: Mapped[datetime | None]


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    email: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)
    # NULL = xem được mọi kho; có giá trị = bị khoá vào đúng kho đó
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
