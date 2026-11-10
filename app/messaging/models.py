"""Hàng đợi + chống trùng: inbound_messages, UNIQUE(channel, external_id). outbound_messages: chưa có bảng."""

from datetime import datetime

from sqlalchemy import ForeignKey, SmallInteger, func
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base
from app.staff import models as _staff  # noqa: F401 — nạp bảng đích của ForeignKey

MSG_CHANNEL = ENUM("zalo", "web", name="msg_channel", create_type=False)
INBOUND_STATUS = ENUM(
    "pending", "processing", "done", "failed", "ignored", name="inbound_status", create_type=False
)


class InboundMessage(Base):
    __tablename__ = "inbound_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(MSG_CHANNEL)
    external_id: Mapped[str]  # = InboundMessage.message_id của kênh
    chat_id: Mapped[str]
    sender_id: Mapped[str | None]
    sender_name: Mapped[str | None]
    event_name: Mapped[str]  # EventKind đã chuẩn hoá (text, image, sticker, …)
    text: Mapped[str | None]
    payload: Mapped[dict] = mapped_column(JSONB)
    sent_at: Mapped[datetime | None]
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"))
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"))
    status: Mapped[str] = mapped_column(INBOUND_STATUS, server_default="pending")
    attempts: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    locked_at: Mapped[datetime | None]
    processed_at: Mapped[datetime | None]
    route: Mapped[str | None]
    error: Mapped[str | None]
