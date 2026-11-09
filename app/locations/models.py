"""Bảng locations (khớp migration 0001_init)."""

from datetime import datetime
from typing import Literal

from sqlalchemy import BigInteger, Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base

LocationKind = Literal["warehouse", "branch", "partner"]


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    code: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[LocationKind] = mapped_column(
        Enum("warehouse", "branch", "partner", name="location_kind", create_type=False)
    )
    archived_at: Mapped[datetime | None]
