# 0005. Append-only inventory ledger with reversing rows
> Status: Accepted
> Date: 2026-11-01

## Context
Stock must be real-time and auditable; staff make mistakes; month-end numbers must be explainable.

## Decision
We will treat `inventory_log` as the single source of truth and never UPDATE/DELETE it. `Hủy` (≤ 30 min, own rows) and
dashboard fixes insert a reversing row (`reverses_id`, flipped action). Stock = plain view `current_stock`
(Σ IN − Σ OUT on `qty_base`). Quantities `NUMERIC`, times `timestamptz`; `units.factor` converts to `base_unit`.

## Alternatives considered
- Mutable stock table — loses history, race-prone. Materialized view — unnecessary at 1 shop.

## Consequences
- Full audit trail; reversals sum correctly by construction.
- Any code path touching `inventory_log` writes needs a spec. Multi-tenant later = `stores` + `store_id`.
