"""init schema MVP (11 bảng theo dataset/dbschema)

Viết tay bằng SQL vì có những thứ autogenerate không sinh được: enum, CHECK, partial unique index,
trigger chặn UPDATE/DELETE trên inventory_log, RLS, view current_stock.

Revision ID: 0001_init
Revises:
Create Date: 2026-11-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_init"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Bảng nghiệp vụ có tenant_id → bật Row-Level Security
TENANT_TABLES = [
    "locations",
    "admins",
    "staff",
    "invite_codes",
    "items",
    "item_aliases",
    "pending_actions",
    "inventory_log",
]

UPGRADE_SQL = r"""
-- ===== Enum =====
CREATE TYPE staff_role     AS ENUM ('staff', 'manager');
CREATE TYPE location_kind  AS ENUM ('warehouse', 'branch', 'partner');
CREATE TYPE inv_action     AS ENUM ('IN', 'OUT', 'WASTE', 'ADJUST', 'TRANSFER', 'PRODUCE');
CREATE TYPE parser_source  AS ENUM ('regex', 'ner', 'llm', 'manual', 'opening', 'undo');
CREATE TYPE msg_channel    AS ENUM ('zalo', 'web');
CREATE TYPE inbound_status AS ENUM ('pending', 'processing', 'done', 'failed', 'ignored');
CREATE TYPE pending_status AS ENUM ('waiting', 'confirmed', 'rejected', 'expired');
CREATE TYPE alias_source   AS ENUM ('admin', 'import', 'learned');

-- ===== Người dùng & kho =====
CREATE TABLE tenants (
    id          bigserial   PRIMARY KEY,
    name        text        NOT NULL,
    timezone    text        NOT NULL DEFAULT 'Asia/Ho_Chi_Minh',
    created_at  timestamptz NOT NULL DEFAULT now(),
    archived_at timestamptz
);

CREATE TABLE locations (
    id          bigserial     PRIMARY KEY,
    tenant_id   bigint        NOT NULL REFERENCES tenants(id),
    code        text          NOT NULL,
    name        text          NOT NULL,
    kind        location_kind NOT NULL,
    aliases     text[]        NOT NULL DEFAULT '{}',
    address     text,
    created_at  timestamptz   NOT NULL DEFAULT now(),
    archived_at timestamptz,
    CONSTRAINT locations_tenant_id_code_key UNIQUE (tenant_id, code)
);

CREATE TABLE admins (
    id            bigserial   PRIMARY KEY,
    tenant_id     bigint      NOT NULL REFERENCES tenants(id),
    email         text        NOT NULL,
    name          text        NOT NULL,
    password_hash text        NOT NULL,
    location_id   bigint      REFERENCES locations(id),
    created_at    timestamptz NOT NULL DEFAULT now(),
    last_login_at timestamptz
);
CREATE UNIQUE INDEX admins_lower_email_key ON admins (lower(email));

CREATE TABLE staff (
    id                  bigserial   PRIMARY KEY,
    tenant_id           bigint      NOT NULL REFERENCES tenants(id),
    default_location_id bigint      NOT NULL REFERENCES locations(id),
    name                text        NOT NULL,
    role                staff_role  NOT NULL DEFAULT 'staff',
    zalo_user_id        text,
    zalo_chat_id        text,
    active              boolean     NOT NULL DEFAULT true,
    linked_at           timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT staff_tenant_id_zalo_user_id_key UNIQUE (tenant_id, zalo_user_id)
);
CREATE INDEX staff_tenant_id_idx ON staff (tenant_id);
CREATE UNIQUE INDEX staff_zalo_chat_id_key ON staff (zalo_chat_id) WHERE zalo_chat_id IS NOT NULL;

CREATE TABLE invite_codes (
    id         bigserial   PRIMARY KEY,
    tenant_id  bigint      NOT NULL REFERENCES tenants(id),
    staff_id   bigint      NOT NULL REFERENCES staff(id),
    code       text        NOT NULL UNIQUE CHECK (code ~ '^[A-Z0-9]{6}$'),
    expires_at timestamptz NOT NULL,
    used_at    timestamptz,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- ===== Danh mục =====
CREATE TABLE items (
    id          bigserial     PRIMARY KEY,
    tenant_id   bigint        NOT NULL REFERENCES tenants(id),
    code        text,
    name        text          NOT NULL,
    category    text,
    base_unit   text          NOT NULL,
    min_qty     numeric(14,3) NOT NULL DEFAULT 0,
    pinned      boolean       NOT NULL DEFAULT false,
    attributes  jsonb         NOT NULL DEFAULT '{}',
    created_at  timestamptz   NOT NULL DEFAULT now(),
    updated_at  timestamptz   NOT NULL DEFAULT now(),
    archived_at timestamptz
);
CREATE INDEX items_tenant_id_idx ON items (tenant_id);
CREATE INDEX items_tenant_id_category_idx ON items (tenant_id, category);
CREATE UNIQUE INDEX items_tenant_id_lower_name_key ON items (tenant_id, lower(name))
    WHERE archived_at IS NULL;

CREATE TABLE units (
    id         bigserial     PRIMARY KEY,
    item_id    bigint        NOT NULL REFERENCES items(id),
    unit_name  text          NOT NULL,
    factor     numeric(14,6) NOT NULL CHECK (factor > 0),
    created_at timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT units_item_id_unit_name_key UNIQUE (item_id, unit_name)
);

-- ===== Zalo & sổ kho =====
CREATE TABLE inbound_messages (
    id           bigserial      PRIMARY KEY,
    channel      msg_channel    NOT NULL,
    external_id  text           NOT NULL,
    chat_id      text           NOT NULL,
    sender_id    text,
    sender_name  text,
    event_name   text           NOT NULL,
    text         text,
    payload      jsonb          NOT NULL,
    sent_at      timestamptz,
    received_at  timestamptz    NOT NULL DEFAULT now(),
    tenant_id    bigint         REFERENCES tenants(id),
    staff_id     bigint         REFERENCES staff(id),
    status       inbound_status NOT NULL DEFAULT 'pending',
    attempts     smallint       NOT NULL DEFAULT 0,
    locked_at    timestamptz,
    processed_at timestamptz,
    route        text,
    error        text,
    CONSTRAINT inbound_messages_channel_external_id_key UNIQUE (channel, external_id)
);
CREATE INDEX inbound_messages_pending_idx ON inbound_messages (received_at) WHERE status = 'pending';
CREATE INDEX inbound_messages_chat_id_received_at_idx ON inbound_messages (chat_id, received_at);

CREATE TABLE item_aliases (
    id              bigserial    PRIMARY KEY,
    tenant_id       bigint       NOT NULL REFERENCES tenants(id),
    item_id         bigint       NOT NULL REFERENCES items(id),
    alias           text         NOT NULL CHECK (alias = lower(btrim(alias))),
    source          alias_source NOT NULL DEFAULT 'admin',
    approved        boolean      NOT NULL DEFAULT true,
    from_inbound_id bigint       REFERENCES inbound_messages(id),
    created_at      timestamptz  NOT NULL DEFAULT now(),
    CONSTRAINT item_aliases_tenant_id_alias_key UNIQUE (tenant_id, alias)
);
CREATE INDEX item_aliases_item_id_idx ON item_aliases (item_id);

CREATE TABLE pending_actions (
    id            bigserial      PRIMARY KEY,
    tenant_id     bigint         NOT NULL REFERENCES tenants(id),
    staff_id      bigint         NOT NULL REFERENCES staff(id),
    chat_id       text           NOT NULL,
    inbound_id    bigint         NOT NULL REFERENCES inbound_messages(id),
    parsed        jsonb          NOT NULL,
    parser_source parser_source  NOT NULL,
    confidence    numeric(4,3),
    status        pending_status NOT NULL DEFAULT 'waiting',
    expires_at    timestamptz    NOT NULL,
    resolved_at   timestamptz,
    created_at    timestamptz    NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX pending_actions_chat_id_waiting_key ON pending_actions (chat_id)
    WHERE status = 'waiting';

CREATE TABLE inventory_log (
    id                      bigserial     PRIMARY KEY,
    tenant_id               bigint        NOT NULL REFERENCES tenants(id),
    location_id             bigint        NOT NULL REFERENCES locations(id),
    item_id                 bigint        NOT NULL REFERENCES items(id),
    action                  inv_action    NOT NULL,
    qty                     numeric(14,3) NOT NULL CHECK (qty > 0),
    unit                    text          NOT NULL,
    qty_base                numeric(14,3) NOT NULL CHECK (qty_base > 0),
    delta_base              numeric(14,3) NOT NULL,
    transfer_id             uuid,
    counterpart_location_id bigint        REFERENCES locations(id),
    pending_action_id       bigint        REFERENCES pending_actions(id),
    event_time              timestamptz   NOT NULL,
    shift                   text,
    received_at             timestamptz   NOT NULL DEFAULT now(),
    staff_id                bigint        REFERENCES staff(id),
    admin_id                bigint        REFERENCES admins(id),
    inbound_id              bigint        REFERENCES inbound_messages(id),
    raw_message             text,
    parser_source           parser_source NOT NULL,
    confidence              numeric(4,3),
    reverses_id             bigint        UNIQUE REFERENCES inventory_log(id),
    note                    text,
    CONSTRAINT inventory_log_actor_check CHECK (staff_id IS NOT NULL OR admin_id IS NOT NULL),
    CONSTRAINT inventory_log_delta_abs_check CHECK (abs(delta_base) = qty_base),
    CONSTRAINT inventory_log_delta_sign_check CHECK (
        (action IN ('IN', 'PRODUCE') AND delta_base > 0)
        OR (action IN ('OUT', 'WASTE') AND delta_base < 0)
        OR action IN ('ADJUST', 'TRANSFER')
    ),
    CONSTRAINT inventory_log_transfer_check CHECK (
        action <> 'TRANSFER' OR (transfer_id IS NOT NULL AND counterpart_location_id IS NOT NULL)
    )
);
CREATE INDEX inventory_log_tenant_id_event_time_idx ON inventory_log (tenant_id, event_time);
CREATE INDEX inventory_log_item_location_time_idx ON inventory_log (item_id, location_id, event_time);
CREATE INDEX inventory_log_transfer_id_idx ON inventory_log (transfer_id);

-- Sổ cái chỉ được thêm: chặn UPDATE/DELETE (TRUNCATE vẫn được, để reset khi nạp lại dữ liệu)
CREATE FUNCTION inventory_log_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'inventory_log chỉ được INSERT; muốn sửa thì thêm dòng bù trừ (reverses_id)';
END $$;
CREATE TRIGGER inventory_log_no_update_delete
    BEFORE UPDATE OR DELETE ON inventory_log
    FOR EACH ROW EXECUTE FUNCTION inventory_log_append_only();

-- Tồn hiện tại = SUM(delta_base) theo (item, location)
CREATE VIEW current_stock AS
SELECT tenant_id, location_id, item_id,
       SUM(delta_base) AS qty_base,
       MAX(event_time) AS last_event_time
FROM inventory_log
GROUP BY tenant_id, location_id, item_id;
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)
    # RLS: chủ bảng (user app 'storagemate') vẫn bypass vì không FORCE.
    # Role khác (vd qa_reader) phải SET app.tenant_id = '<id>' mới thấy dữ liệu.
    for t in TENANT_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {t}_tenant_isolation ON {t} "
            f"USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::bigint)"
        )


def downgrade() -> None:
    op.execute("""
        DROP VIEW IF EXISTS current_stock;
        DROP TABLE IF EXISTS inventory_log, pending_actions, item_aliases, inbound_messages, units, items,
            invite_codes, staff, admins, locations, tenants CASCADE;
        DROP FUNCTION IF EXISTS inventory_log_append_only();
        DROP TYPE IF EXISTS staff_role, location_kind, inv_action, parser_source, msg_channel,
            inbound_status, pending_status, alias_source;
    """)
