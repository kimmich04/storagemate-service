"""Bản chờ OK/Sai: phiếu do LLM (sau này NER) đọc chỉ được ghi sổ khi đúng người gửi trả OK.

Mỗi chat tối đa một bản 'waiting' (unique index). Bản mới, hoặc tin khác OK/Sai, kết thúc bản cũ.
Module này không ghi sổ: worker (messaging/queue.py) gọi ledger.record rồi resolve(..., "confirmed").
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.inventory.models import PendingAction
from app.parser.regex import Phieu, RawLine
from app.staff.models import Staff


def create(
    session: Session,
    *,
    staff: Staff,
    chat_id: str,
    inbound_id: int,
    phieu: Phieu,
    source: str,
    now: datetime,
) -> PendingAction:
    session.execute(
        update(PendingAction)
        .where(PendingAction.chat_id == chat_id, PendingAction.status == "waiting")
        .values(status="expired", resolved_at=now)
    )
    row = PendingAction(
        tenant_id=staff.tenant_id,
        staff_id=staff.id,
        chat_id=chat_id,
        inbound_id=inbound_id,
        parsed=phieu_to_json(phieu),
        parser_source=source,
        status="waiting",
        expires_at=now + timedelta(minutes=settings.PENDING_TTL_MINUTES),
    )
    session.add(row)
    session.flush()
    return row


def find_waiting(session: Session, chat_id: str) -> PendingAction | None:
    return session.scalars(
        select(PendingAction).where(PendingAction.chat_id == chat_id, PendingAction.status == "waiting")
    ).first()


def resolve(row: PendingAction, status: str, now: datetime) -> None:
    row.status, row.resolved_at = status, now


def phieu_to_json(phieu: Phieu) -> dict:
    """Số lượng lưu dạng chuỗi để không mất độ chính xác Decimal; ngày dạng ISO."""
    return {
        "action": phieu.action,
        "date": phieu.date.isoformat(),
        "date_note": phieu.date_note,
        "from_loc": phieu.from_loc,
        "to_loc": phieu.to_loc,
        "lines": [
            {"raw": line.raw, "name": line.name, "qty": str(line.qty), "unit": line.unit, "note": line.note}
            for line in phieu.lines
        ],
        "bad_lines": phieu.bad_lines,
        "warnings": phieu.warnings,
    }


def phieu_from_json(data: dict) -> Phieu:
    return Phieu(
        action=data["action"],
        date=date.fromisoformat(data["date"]),
        date_note=data["date_note"],
        from_loc=data["from_loc"],
        to_loc=data["to_loc"],
        lines=[
            RawLine(
                raw=line["raw"],
                name=line["name"],
                qty=Decimal(line["qty"]),
                unit=line["unit"],
                note=line["note"],
            )
            for line in data["lines"]
        ],
        bad_lines=list(data["bad_lines"]),
        warnings=list(data["warnings"]),
    )
