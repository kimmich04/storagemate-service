"""Danh mục mặt hàng (items) và quy đổi đơn vị (units) — map bảng của migration 0001_init."""

from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base
from app.staff import models as _staff  # noqa: F401 — nạp bảng đích của ForeignKey


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    code: Mapped[str | None]  # = CatalogItem.code = Excel cột MÃ VT
    name: Mapped[str]
    category: Mapped[str | None]  # tiêu đề nhóm trong Excel (MERCHANDISE, HÀNG SẢN XUẤT, …)
    base_unit: Mapped[str]
    min_qty: Mapped[Decimal] = mapped_column(Numeric(14, 3), server_default="0")


class Unit(Base):
    __tablename__ = "units"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    unit_name: Mapped[str]
    factor: Mapped[Decimal] = mapped_column(Numeric(14, 6))
