"""khóa Data API của Supabase: view tôn trọng RLS, thu quyền anon/authenticated

Supabase tự mở schema public qua REST cho role anon/authenticated. Bảng đã có RLS nên an toàn,
nhưng view chạy bằng quyền chủ sở hữu (bỏ qua RLS) → current_stock lộ hết tồn kho với anon key.
App không dùng Data API, nên thu toàn bộ quyền. Trên Postgres thường (không có các role này) thì bỏ qua.

Revision ID: 0002_lock_data_api
Revises: 0001_init
Create Date: 2026-11-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_lock_data_api"
down_revision: str | None = "0001_init"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UPGRADE_SQL = r"""
-- View chạy theo quyền người gọi → RLS của inventory_log được áp dụng (cần PG15+)
ALTER VIEW current_stock SET (security_invoker = true);

DO $$
DECLARE
    r text;
BEGIN
    FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I', r);
            EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM %I', r);
            EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM %I', r);
            -- bảng tạo về sau (bởi role đang chạy migration) cũng không tự cấp quyền nữa
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM %I', r);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM %I', r);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM %I', r);
        END IF;
    END LOOP;
END $$;
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    # Cố ý không cấp lại quyền cho anon/authenticated: cấp lại = mở lại lỗ hổng.
    op.execute("ALTER VIEW current_stock SET (security_invoker = false)")
