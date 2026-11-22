"""role qa_reader + view qa_* cho Q&A agent (chỉ đọc)

Q&A đăng nhập bằng role riêng `qa_reader` (DATABASE_URL_READONLY) và chỉ được SELECT 4 view dưới đây.
View chạy bằng quyền chủ sở hữu (không security_invoker) nên tự lọc tenant theo `app.tenant_id` do code đặt;
thiếu setting → NULL → không trả dòng nào. qa_reader không có quyền gì trên bảng gốc.

Mật khẩu KHÔNG nằm ở đây: owner chạy tay `ALTER ROLE qa_reader WITH LOGIN PASSWORD '...'`.
Role là của cả cluster (DB test và DB demo dùng chung) nên tạo khi chưa có và giữ lại khi downgrade.

Revision ID: 0003_qa_reader
Revises: 0002_lock_data_api
Create Date: 2026-11-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_qa_reader"
down_revision: str | None = "0002_lock_data_api"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::bigint"
VIEWS = ("qa_items", "qa_locations", "qa_stock", "qa_movements")

UPGRADE_SQL = f"""
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'qa_reader') THEN
        CREATE ROLE qa_reader NOLOGIN;
    END IF;
END $$;
ALTER ROLE qa_reader SET statement_timeout = '5s';
ALTER ROLE qa_reader SET default_transaction_read_only = on;

CREATE VIEW qa_items AS
SELECT i.id AS item_id, i.code, i.name, i.category, i.base_unit, i.min_qty,
       COALESCE(array_agg(a.alias ORDER BY a.alias) FILTER (WHERE a.alias IS NOT NULL), '{{}}') AS aliases
FROM items i
LEFT JOIN item_aliases a ON a.item_id = i.id AND a.approved
WHERE i.archived_at IS NULL AND i.tenant_id = {TENANT}
GROUP BY i.id;

CREATE VIEW qa_locations AS
SELECT l.id AS location_id, l.code, l.name, l.kind::text AS kind, l.aliases
FROM locations l
WHERE l.archived_at IS NULL AND l.tenant_id = {TENANT};

CREATE VIEW qa_stock AS
SELECT s.item_id, i.name AS item_name, i.base_unit, i.min_qty,
       l.code AS location_code, l.name AS location_name, s.qty_base, s.last_event_time
FROM (
    SELECT item_id, location_id, SUM(delta_base) AS qty_base, MAX(event_time) AS last_event_time
    FROM inventory_log
    WHERE tenant_id = {TENANT}
    GROUP BY item_id, location_id
) s
JOIN items i ON i.id = s.item_id
JOIN locations l ON l.id = s.location_id;

CREATE VIEW qa_movements AS
SELECT g.id AS log_id, g.event_time, g.action::text AS action, g.item_id, i.name AS item_name, i.base_unit,
       l.code AS location_code, l.name AS location_name,
       c.code AS counterpart_code, c.name AS counterpart_name,
       g.qty, g.unit, g.qty_base, g.delta_base, s.name AS staff_name, g.reverses_id
FROM inventory_log g
JOIN items i ON i.id = g.item_id
JOIN locations l ON l.id = g.location_id
LEFT JOIN locations c ON c.id = g.counterpart_location_id
LEFT JOIN staff s ON s.id = g.staff_id
WHERE g.tenant_id = {TENANT};

GRANT SELECT ON {", ".join(VIEWS)} TO qa_reader;
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    # Giữ role qa_reader: dùng chung cả cluster và có thể đang có mật khẩu do owner đặt.
    op.execute(f"DROP VIEW IF EXISTS {', '.join(VIEWS)}")
