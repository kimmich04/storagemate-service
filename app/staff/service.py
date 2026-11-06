"""Nhân viên: tra theo chat Zalo, tạo mã mời, đổi mã lấy liên kết Zalo. CRUD nhân viên: spec API dashboard."""

import logging
import re
import secrets
import string
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.staff.models import InviteCode, Staff

logger = logging.getLogger(__name__)

INVITE_TTL = timedelta(hours=24)
CODE_ALPHABET = string.ascii_uppercase + string.digits
CODE_LENGTH = 6
CODE_RE = re.compile(rf"[A-Z0-9]{{{CODE_LENGTH}}}")  # khớp CHECK của bảng invite_codes
MAX_CODE_TRIES = 10


def find_by_chat_id(session: Session, chat_id: str) -> Staff | None:
    """Chỉ nhân viên đang hoạt động mới được ghi phiếu."""
    return session.scalars(select(Staff).where(Staff.zalo_chat_id == chat_id, Staff.active)).first()


def normalize_code(text: str | None) -> str | None:
    """`k7p2 q9` → `K7P2Q9`; không ra đúng 6 ký tự chữ/số thì None (tin này không phải mã)."""
    code = "".join((text or "").split()).upper()
    return code if CODE_RE.fullmatch(code) else None


def create_invite(session: Session, staff: Staff, now: datetime) -> InviteCode:
    """Mỗi nhân viên chỉ còn 1 mã hiệu lực: mã cũ chưa dùng bị thu hồi."""
    unused = select(InviteCode).where(
        InviteCode.staff_id == staff.id, InviteCode.used_at.is_(None), InviteCode.revoked_at.is_(None)
    )
    for old in session.scalars(unused):
        old.revoked_at = now
    invite = InviteCode(
        tenant_id=staff.tenant_id, staff_id=staff.id, code=_unused_code(session), expires_at=now + INVITE_TTL
    )
    session.add(invite)
    session.flush()
    return invite


def _unused_code(session: Session) -> str:
    for _ in range(MAX_CODE_TRIES):
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if session.scalar(select(InviteCode.id).where(InviteCode.code == code)) is None:
            return code
    raise RuntimeError("Không sinh được mã mời chưa dùng")


def redeem_invite(
    session: Session, code: str, chat_id: str, sender_id: str | None, now: datetime
) -> Staff | None:
    """Mã hợp lệ → gắn chat vào nhân viên của mã. None = từ chối (cùng một câu trả lời cho mọi lý do)."""
    found = session.execute(
        select(InviteCode, Staff)
        .join(Staff, Staff.id == InviteCode.staff_id)
        .where(InviteCode.code == code)
        .with_for_update(of=InviteCode)
    ).first()
    if found is None:
        return None
    invite, staff = found
    if invite.used_at or invite.revoked_at or invite.expires_at <= now or not staff.active:
        return None
    user_id = sender_id or None
    if not _release_from_former_staff(session, staff, chat_id, user_id):
        return None
    staff.zalo_chat_id, staff.zalo_user_id, staff.linked_at = chat_id, user_id, now
    invite.used_at = now
    session.flush()
    return staff


def _release_from_former_staff(session: Session, staff: Staff, chat_id: str, user_id: str | None) -> bool:
    """Chat/Zalo đang nằm trên hồ sơ khác: hồ sơ đã nghỉ → gỡ ra (người cũ được nhận lại); còn làm → False."""
    clauses = [Staff.zalo_chat_id == chat_id]  # UNIQUE toàn bảng
    if user_id:
        clauses.append(
            (Staff.tenant_id == staff.tenant_id) & (Staff.zalo_user_id == user_id)
        )  # UNIQUE / tenant
    holders = list(session.scalars(select(Staff).where(Staff.id != staff.id, or_(*clauses))))
    if any(holder.active for holder in holders):
        logger.warning("Zalo của chat %s đang gắn với nhân viên khác còn làm — từ chối mã mời", chat_id)
        return False
    for holder in holders:
        holder.zalo_chat_id = holder.zalo_user_id = None
    session.flush()  # gỡ trước khi gắn để không dính UNIQUE
    return True
