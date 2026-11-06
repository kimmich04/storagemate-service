# Database Design
> last-updated: 2026-11-07 · status: **migrated** — `alembic/versions/2026-11-04_init_schema.py` (rev `0001_init`) implements the 11-table MVP schema in `dataset/dbschema` (DBML, tenant-based). The tables section below predates it; where they differ, `dataset/dbschema` + the migration win. ORM models (2.0 `Mapped`) map the existing tables; they never create them.

If this doc and the Alembic migrations diverge, the migration wins — fix this doc.

## Engine & access
PostgreSQL 16 via SQLAlchemy 2.0 sync + psycopg 3 (`app/database.py`, `pool_pre_ping`). Alembic migrations.
Two roles: app (`DATABASE_URL`) and `qa_reader` (`DATABASE_URL_READONLY`, SELECT on business views only,
`statement_timeout` 5 s, max 200 rows). Constraint names from `NAMING_CONVENTION` in `app/models.py`.

## ERD
```mermaid
erDiagram
  STAFF ||--o{ INVITE_CODES : has
  STAFF ||--o{ INVENTORY_LOG : records
  STAFF ||--o{ PENDING_ACTIONS : awaits
  ITEMS ||--o{ UNITS : converts
  ITEMS ||--o{ INVENTORY_LOG : moves
  INBOUND_MESSAGES ||--o{ INVENTORY_LOG : source
  INVENTORY_LOG ||--o| INVENTORY_LOG : reverses
```

## Tables
| Table | Key columns | Purpose | Domain |
|-------|-------------|---------|--------|
| admins | id, email, password_hash, created_at | Dashboard login (1 admin via script) | auth |
| staff | id, name, role(staff/manager), zalo_user_id UNIQUE, zalo_chat_id, active, linked_at | Identity | staff |
| invite_codes | id, staff_id, code, expires_at, used_at, failed_attempts | One-time Zalo linking | staff |
| items | id, name, base_unit, aliases, min_stock | Catalog | items |
| units | id, item_id, unit_name, factor | Unit conversion (1 thùng = 24 hộp) | items |
| inbound_messages | id, channel, message_id, chat_id, sender_id, event_name, text, payload jsonb, received_at, status, attempts, error | Queue + dedup | messaging |
| outbound_messages | id, chat_id, text, sent_at, zalo_message_id, status, error | Bot send log | messaging |
| pending_actions | id, staff_id, chat_id, parsed jsonb, parser_source, confidence, expires_at, status | Await OK/Sai | inventory |
| inventory_log | id, item_id, action IN/OUT, qty, unit, qty_base, event_time, received_at, staff_id, inbound_id, raw_message, parser_source, confidence, reverses_id | **Ledger, source of truth** | inventory |
| training_samples | id, raw_message, labels, parser_source, verified, corrected_by, created_at | NER flywheel | labels |

View `current_stock`: `items LEFT JOIN inventory_log`, `SUM(IN qty_base) − SUM(OUT qty_base)` (plain view, not materialized).

## Invariants & constraints
- `inventory_log` is **append-only** — no UPDATE/DELETE. Cancel/fix = new row with `reverses_id` and flipped action.
- `UNIQUE(channel, message_id)` on `inbound_messages`.
- `qty > 0`; OUT must not make stock negative (checked in validate before insert).
- `event_time` ≤ now and ≥ now − 7 days; `event_time` (from text) separate from `received_at` (webhook).
- Quantities `NUMERIC`, times `timestamptz`. `qty_base` stored in the item's base unit.
- Invite codes: 6 chars, single use, 24 h TTL; >5 failures in 15 min → lock chat_id.

## Indexing & performance notes
1 shop, low volume. Expected hot paths: queue claim (`status`, `received_at`), ledger by `item_id`/`event_time`,
staff by `zalo_chat_id`. <!-- unknown: finalize indexes when writing the first migration -->

## Migrations
`alembic revision --autogenerate -m "..."` → review → `alembic upgrade head`. Never edit an applied migration.
Migration `0001_init` is hand-written SQL (enums, CHECKs, partial unique indexes, append-only trigger on
`inventory_log`, RLS policies on `app.tenant_id`, view `current_stock`). ORM models map only the columns the
code uses (no enums/trigger/view/RLS), so **do not run `--autogenerate`** — the diff would be noise. Write migrations by hand.

## Seed data (T10/2026) — dev DB only
Data-only dump `seed_t10_2026.sql` (generated elsewhere by `scripts/import_excel.py`, which is **not** in this repo):
tenant Eggyolk, 4 locations (`KT_SG` kho tổng, `220_LTT`, `PQ`, `DOI_TAC`; aliases with and without accents),
admin `import@storagemate.local`, 359 items in 8 categories (kho tổng and 220 have separate item rows), units,
448 item_aliases, and the October ledger (opening `ADJUST` 30/09 + `manual` IN/OUT/WASTE) — kho tổng `current_stock`
equals Excel column "Tồn cuối 31.10" for all 123 codes (checked 2026-11-06). Load after `alembic upgrade head`:
`psql -U storagemate -d storagemate -v ON_ERROR_STOP=1 -1 -q -f seed_t10_2026.sql` (use `-f`, not a PowerShell pipe → keeps UTF-8).
Then `scripts/dev_db.py`: `--map-codes` (seed leaves `items.code` NULL; ids 1–123 = MÃ VT of kho tổng → the ledger
finds items by code), `--invite NAME [--role manager]` (staff row + invite code; replaces the dashboard until it exists), `--link-staff NAME CHAT_ID` (dev shortcut, no code), optional `--fake-moves` (IN+OUT pairs,
same item/qty, note `DỮ LIỆU ẢO (dev)`, 01/11 → yesterday, stock unchanged), `--reset` (TRUNCATE, localhost only).
Only **kho tổng** is written by the bot: `location_id` = staff's default location; the other side is
`counterpart_location_id` (aliases compared with `fold()`). Old Excel loader: `scripts/_archive/import_opening.py`.
