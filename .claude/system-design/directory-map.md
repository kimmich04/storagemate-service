# Directory Map
> last-updated: 2026-11-09

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
| `app/staff/` | `Tenant`, `Location`, `Staff`, `InviteCode` models; `service`: `find_by_chat_id`, `create_invite`, `redeem_invite` | 🖥️ `/api/staff` (later) |
| `app/inventory/` | Ledger, confirm ✅ (`confirm.py`: bản chờ OK/Sai; Hủy chưa có), stock & transactions | 🖥️ `/api/stock`, `/api/transactions` |
| `app/labels/` | Training-sample review | 🖥️ `/api/labels` |
| `app/reports/` | Report service + APScheduler jobs | 🖥️ `/api/reports` |
| `app/chat/` | Web chat demo in/out | 🖥️ `/api/chat` |
| `app/channels/` | Zalo webhook, adapters (`base`, `zalo`, `web`), `zalo_client` | ⚡ `/webhooks/zalo` |
| `app/messaging/` | `inbox` (enqueue/claim), `queue.process_next`, dispatcher (routing), replies | ⚙️ worker (+ `inbox.enqueue` from the webhook) |
| `app/parser/` | regex ✅ · llm ✅ (`llm.py`: Gemini → `Phieu`) · ner / validate / service: chưa có | ⚙️ worker only |
| `app/qa/` | Manager Q&A (tools + LangChain fallback) | ⚙️ worker only |
| `tests/` | pytest, mirrors `app/` | |
| `alembic/` | Migrations | `0001_init` (hand-written SQL) |
| `ml/` | NER training (Colab), not deployed | `.[ml]` extra |
| `models/` | `.onnx` files, gitignored | pulled from HF Hub |
| `scripts/` | `dev_db` (after loading seed: `--map-codes`, `--invite`, `--link-staff`, `--fake-moves`, `--reset`), zalo_poll, zalo_set_webhook; `_archive/` = old Excel loader | |
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
