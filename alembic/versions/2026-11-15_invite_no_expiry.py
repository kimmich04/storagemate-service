"""mã mời không hết hạn: invite_codes.expires_at cho phép NULL (NULL = không hết hạn)

Mã vẫn chỉ dùng 1 lần và bị thu hồi khi tạo mã mới cho cùng nhân viên. Cột được giữ để sau này admin có
thể tự đặt hạn cho từng mã. Mã đang chờ dùng (chưa dùng, chưa thu hồi) cũng bỏ hạn theo chính sách mới.

Revision ID: 0004_invite_no_expiry
Revises: 0003_qa_reader
Create Date: 2026-11-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_invite_no_expiry"
down_revision: str | None = "0003_qa_reader"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE invite_codes ALTER COLUMN expires_at DROP NOT NULL")
    op.execute("UPDATE invite_codes SET expires_at = NULL WHERE used_at IS NULL AND revoked_at IS NULL")


def downgrade() -> None:
    op.execute(
        "UPDATE invite_codes SET expires_at = created_at + interval '24 hours' WHERE expires_at IS NULL"
    )
    op.execute("ALTER TABLE invite_codes ALTER COLUMN expires_at SET NOT NULL")
