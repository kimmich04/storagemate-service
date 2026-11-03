# Directory Map
> last-updated: 2026-11-01

Domain-first layout (FastAPI "Bigger Applications" + fastapi-best-practices). Per-domain file roles:
`.claude/rules/python-fastapi.md` §2. For live "who calls what": `graphify query "..."`.

## Top-level layout
| Path | Responsibility | Notes |
|------|----------------|-------|
| `app/main.py` | App, CORS, mounts `/api` + webhook, `/health` | operationId = `<tag>-<func>` for TS client |
| `app/api.py` | Mounts all dashboard routers under `/api` | only place UI routers are registered |
| `app/config.py` · `database.py` · `models.py` · `exceptions.py` | Settings, session/`get_db`, `Base`, `AppError` | shared core |
| `app/worker.py` | Worker process entry | queue loop + APScheduler |
| `app/auth/` | Admin login, JWT, `get_current_user` | 🖥️ `/api/auth` |
| `app/items/` | Catalog, aliases, units | 🖥️ `/api/items` |
| `app/staff/` | Staff, invite codes | 🖥️ `/api/staff` |
| `app/inventory/` | Ledger, confirm (OK/Sai/Hủy), stock & transactions | 🖥️ `/api/stock`, `/api/transactions` |
| `app/labels/` | Training-sample review | 🖥️ `/api/labels` |
| `app/reports/` | Report service + APScheduler jobs | 🖥️ `/api/reports` |
| `app/chat/` | Web chat demo in/out | 🖥️ `/api/chat` |
| `app/channels/` | Zalo webhook, adapters (`base`, `zalo`, `web`), `zalo_client` | ⚡ `/webhooks/zalo` |
| `app/messaging/` | Queue claim, dispatcher (routing) | ⚙️ worker only |
| `app/parser/` | regex → ner (ONNX) → llm → validate | ⚙️ worker only |
| `app/qa/` | Manager Q&A (tools + LangChain fallback) | ⚙️ worker only |
| `tests/` | pytest, mirrors `app/` | |
| `alembic/` | Migrations | `versions/` empty so far |
| `ml/` | NER training (Colab), not deployed | `.[ml]` extra |
| `models/` | `.onnx` files, gitignored | pulled from HF Hub |
| `scripts/` | create_admin, seed_items, zalo_poll, zalo_set_webhook | |
| `.github/workflows/ci.yml` | ruff + pytest on PR / push main | |
| `docs/` | Proposal v2 as Markdown + `assets/figure-1..4.png` | Human scope source; edit scope here first |

## Module boundaries
- Domains talk via each other's `service`/`schemas`, never `router`.
- `messaging/`, `parser/`, `qa/` must not import FastAPI (worker-side).
- `channels/` is the only code that knows Zalo payload shapes; everything after it sees `InboundMessage`.

## "Don't touch" zones
- Applied Alembic migrations. `inventory_log` write path (append-only invariant) needs a spec before changing.
- `custom_generate_unique_id` in `main.py` — changing it breaks the dashboard's generated client.
- `graphify-out/` is generated.

## Ownership
Nash (@honguyen17). Dashboard lives in a separate web repo. <!-- unknown: confirm repo name/URL -->
