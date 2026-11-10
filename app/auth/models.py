"""Bảng admins (khớp migration 0001_init). Tạo admin bằng scripts/create_admin.py.

Tenant nằm ở app/staff/models.py (một định nghĩa duy nhất cho mỗi bảng).
"""

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
    # NULL = xem được mọi kho; có giá trị = bị khoá vào đúng kho đó
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
