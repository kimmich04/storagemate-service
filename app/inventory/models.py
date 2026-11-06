"""Sổ cái inventory_log — CHỈ INSERT (trigger DB chặn UPDATE/DELETE); sửa sai = dòng đảo reverses_id."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, func
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column

from app.auth import models as _auth  # noqa: F401 — nạp bảng đích của ForeignKey
from app.items import models as _items  # noqa: F401 — nạp bảng đích của ForeignKey
from app.messaging import models as _messaging  # noqa: F401 — nạp bảng đích của ForeignKey
from app.models import Base
from app.staff import models as _staff  # noqa: F401 — nạp bảng đích của ForeignKey

INV_ACTION = ENUM("IN", "OUT", "WASTE", "ADJUST", "TRANSFER", "PRODUCE", name="inv_action", create_type=False)
PARSER_SOURCE = ENUM(
    "regex", "ner", "llm", "manual", "opening", "undo", name="parser_source", create_type=False
)
QTY = Numeric(14, 3)


class InventoryLog(Base):
    __tablename__ = "inventory_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    action: Mapped[str] = mapped_column(INV_ACTION)
    qty: Mapped[Decimal] = mapped_column(QTY)
    unit: Mapped[str]
    qty_base: Mapped[Decimal] = mapped_column(QTY)
    delta_base: Mapped[Decimal] = mapped_column(QTY)
    counterpart_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    event_time: Mapped[datetime]
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"))
    admin_id: Mapped[int | None] = mapped_column(ForeignKey("admins.id"))
    inbound_id: Mapped[int | None] = mapped_column(ForeignKey("inbound_messages.id"))
    raw_message: Mapped[str | None]
    parser_source: Mapped[str] = mapped_column(PARSER_SOURCE)
    reverses_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_log.id"))
    note: Mapped[str | None]
