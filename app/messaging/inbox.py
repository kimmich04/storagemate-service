"""Hàng đợi tin nhắn trên Postgres: webhook/poll enqueue, worker claim rồi đánh dấu kết quả.

Chống trùng bằng UNIQUE(channel, external_id). Claim giữ khoá FOR UPDATE suốt transaction xử lý:
worker chết giữa chừng → rollback → tin tự quay về 'pending'.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.channels.base import InboundMessage
from app.messaging.models import InboundMessage as InboundRow

MAX_ERROR_CHARS = 500


def enqueue(session: Session, msg: InboundMessage, payload: dict) -> bool:
    """False khi tin đã có (kênh gửi lại) — không làm gì thêm."""
    stmt = (
        insert(InboundRow)
        .values(
            channel=msg.channel,
            external_id=msg.message_id,
            chat_id=msg.chat_id,
            sender_id=msg.sender_id,
            sender_name=msg.display_name,
            event_name=msg.event,
            text=msg.text,
            payload=payload,
            sent_at=msg.sent_at,
        )
        .on_conflict_do_nothing(index_elements=["channel", "external_id"])
        .returning(InboundRow.id)
    )
    return session.execute(stmt).first() is not None


def claim_next(session: Session, now: datetime) -> InboundRow | None:
    row = session.scalars(
        select(InboundRow)
        .where(InboundRow.status == "pending")
        .order_by(InboundRow.received_at, InboundRow.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).first()
    if row is not None:
        row.status, row.locked_at, row.attempts = "processing", now, row.attempts + 1
    return row


def find(session: Session, channel: str, external_id: str) -> InboundRow | None:
    return session.scalars(
        select(InboundRow).where(InboundRow.channel == channel, InboundRow.external_id == external_id)
    ).first()


def to_message(row: InboundRow) -> InboundMessage:
    """Dựng lại InboundMessage từ cột đã chuẩn hoá — không phụ thuộc payload của từng kênh."""
    return InboundMessage(
        channel=row.channel,
        message_id=row.external_id,
        chat_id=row.chat_id,
        sender_id=row.sender_id or "",
        display_name=row.sender_name or "",
        event=row.event_name,
        text=row.text,
        photo_url=None,
        sent_at=row.sent_at or row.received_at,
    )


def finish(row: InboundRow, status: str, now: datetime, route: str | None = None) -> None:
    row.status, row.processed_at = status, now
    if route is not None:
        row.route = route


def mark_failed(session: Session, row_id: int, error: str, now: datetime) -> None:
    """Gọi trong transaction mới, sau khi transaction xử lý đã rollback."""
    row = session.get(InboundRow, row_id)
    if row is None:
        return
    row.status, row.processed_at, row.error = "failed", now, error[:MAX_ERROR_CHARS]
    row.attempts += 1  # lần tăng lúc claim đã bị rollback cùng transaction xử lý
