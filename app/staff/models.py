"""Tenant, kho, nhân viên và mã mời — map đúng bảng của migration 0001_init (không tạo bảng)."""

from datetime import datetime

from sqlalchemy import ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, ENUM
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base

LOCATION_KIND = ENUM("warehouse", "branch", "partner", name="location_kind", create_type=False)
STAFF_ROLE = ENUM("staff", "manager", name="staff_role", create_type=False)


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    timezone: Mapped[str] = mapped_column(server_default="Asia/Ho_Chi_Minh")
    archived_at: Mapped[datetime | None]


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    code: Mapped[str]
    name: Mapped[str]
    kind: Mapped[str] = mapped_column(LOCATION_KIND)
    # alias có thể có dấu (seed T10); ledger so bằng fold()
    aliases: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    archived_at: Mapped[datetime | None]


class Staff(Base):
    __tablename__ = "staff"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    default_location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    name: Mapped[str]
    role: Mapped[str] = mapped_column(STAFF_ROLE, server_default="staff")
    zalo_user_id: Mapped[str | None]
    zalo_chat_id: Mapped[str | None]
    active: Mapped[bool] = mapped_column(server_default="true")
    linked_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class InviteCode(Base):
    """Mã 6 ký tự, dùng 1 lần; manager gửi cho nhân viên, nhân viên nhắn cho bot để gắn Zalo."""

    __tablename__ = "invite_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"))
    code: Mapped[str]
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
