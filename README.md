# Storagemate Service

**English** · [Tiếng Việt](README.vi.md)

Backend of **Storagemate**, an AI agent on Zalo that keeps inventory for F&B businesses.
Staff report stock in/out by chatting with a Zalo bot in Vietnamese. The bot records every move in an append-only
ledger, and managers can ask it questions about stock in plain language. The web dashboard
(separate repo `storagemate-ui`) reads the same data through a REST API.


## Contents

1. [Features](#1-features)
2. [Architecture](#2-architecture)
3. [Getting started](#3-getting-started)
4. [Manager Q&A setup](#4-manager-qa-setup)
5. [Common commands](#5-common-commands)
6. [Environment variables](#6-environment-variables)
7. [Project layout](#7-project-layout)
8. [Troubleshooting](#8-troubleshooting)
9. [Contributing](#9-contributing)

---

## 1. Features

| Feature | How it works | Status |
|---|---|---|
| Zalo bot | Polling (`scripts/zalo_poll.py`, dev) or webhook with a secret header | ✅ polling tested on Zalo · webhook not yet tested on Zalo |
| Message queue | Postgres table, duplicate webhooks ignored, exactly one worker | ✅ |
| Staff linking | New staff send a 6-character invite code to link their Zalo chat. Single use, no expiry | ✅ |
| Stock entries from chat | Regex reads the standard format and writes directly. Gemini reads free-form text; the staff member replies `OK` before anything is saved | ✅ regex · 🟡 LLM: done, waiting for a Zalo test |
| Manager Q&A agent | LangChain + Gemini tool calling over 5 read-only tools, on a separate read-only Postgres login | 🟡 done, 12/12 test questions correct, waiting for a Zalo test |
| Dashboard API | Read endpoints under `/api` (stock, transactions, overview KPIs, items, locations) | ✅ read-only, no login yet |
| Not built yet | NER model (training pipeline in `ml/` only), `Hủy` (undo), scheduled reports, admin login (JWT), label review | 🔲 |

## 2. Architecture

One Docker image, two processes. They talk **only through PostgreSQL** (no Redis or Celery, see ADR 0003).

```mermaid
flowchart LR
  zalo[Zalo Bot API] -->|POST /webhooks/zalo| api
  dash[Dashboard SPA] -->|GET /api/*| api
  subgraph image[storagemate-service image]
    api[api: FastAPI]
    worker[worker: python -m app.worker]
  end
  api -->|INSERT ... ON CONFLICT DO NOTHING| db[(PostgreSQL)]
  worker -->|SELECT ... FOR UPDATE SKIP LOCKED| db
  worker -->|qa_reader login: qa_* views only| db
  worker -->|sendMessage| zalo
  worker --> gemini[Gemini API]
```

### How a message is handled

1. **api** checks the webhook secret, stores the message in `inbound_messages` and returns `200` at once.
   `UNIQUE(channel, external_id)` drops webhooks that Zalo sends twice.
2. **worker** claims the next message with `FOR UPDATE SKIP LOCKED` and processes it in **one transaction**.
3. Unlinked chat → invite-code flow. Linked chat → regex parser first.
4. Regex understood it → write to the ledger `inventory_log` (append-only; a fix is a new reversing row).
5. Regex did not → one Gemini call classifies the message as a stock entry, a question, or other:
   - **stock entry** → saved as pending; written only after the staff member replies `OK` (10-minute limit);
   - **question** from a **manager** → Q&A agent; from regular staff → polite refusal;
   - **other** → "not understood" plus the syntax guide.
6. The bot replies on Zalo **only after the transaction commits**.

### Manager Q&A agent (`app/qa/`)

A hand-written tool-calling loop with LangChain (`bind_tools`) and Gemini:

- Gemini picks tools (`FindItems`, `GetStock`, `GetMovements`, `TopItems`, `StaffActivity`); the code validates the
  arguments with Pydantic, runs the SQL and returns the result. Gemini never touches the database.
- At most 5 steps and 30 seconds per question. On any error it sends no answer rather than a made-up number.
- Defense in depth: the tools connect with a separate login, `qa_reader`, that is read-only, has a 5-second query
  limit and can read only 4 purpose-built views (no base tables, no personal data). The views show no rows unless
  the session's tenant is set, so tenant isolation fails closed. Tenant and today's date come from code, never from the model.

Details: [`.claude/system-design/`](.claude/system-design/README.md) (data flow, database design, ADRs in `decisions/`).
Business scope: [`docs/storagemate-proposal-plan-v2.md`](docs/storagemate-proposal-plan-v2.md).

## 3. Getting started

### Requirements

| Tool | Version | Notes |
|---|---|---|
| Python | **3.11–3.13** | Not 3.14 (`pyproject.toml` blocks it; ML libraries lack support). 3.13 recommended |
| PostgreSQL | 16+ | Local install or Docker |
| Zalo bot token | | From Zalo Bot Creator, to talk to the bot |
| Gemini API key | | From Google AI Studio, for the LLM parser and Q&A. Optional: without it the bot uses regex only |

### Steps

```bash
git clone https://github.com/kimmich04/storagemate-service.git
cd storagemate-service

# Windows: py -3.13 -m venv .venv ; .venv\Scripts\activate
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env            # Windows: copy .env.example .env  → then fill it in (section 6)
```

**Database.** Create an empty database, point `DATABASE_URL` at it, then:

```bash
alembic upgrade head
```

The October 2026 sample data (`dataset/seed.sql`, not in git, shared separately) drops and rebuilds the schema at
`0001_init`, so load it first and run `alembic upgrade head` afterwards:

```bash
psql "<DATABASE_URL without +psycopg>" -v ON_ERROR_STOP=1 -f dataset/seed.sql
alembic upgrade head
```

**Run** (three terminals):

```bash
fastapi dev                     # api: http://127.0.0.1:8000/docs
python -m app.worker            # worker
python scripts/zalo_poll.py     # dev only: pull messages from Zalo (do not use together with the webhook)
```

**Link your Zalo account:** create an invite code and send it to the bot.

```bash
python scripts/dev_db.py --invite "Your name" --role manager
```

Then send a stock entry, e.g. `ngày <dd/mm> nhập hàng về kho tổng` + a new line `Cà phê kem béo: 5`
(use a date within the last 7 days; older dates are rejected).

### Tests

```bash
pytest
```

Tests need a **separate** database in `TEST_DATABASE_URL`; it is **wiped on every run**, so never point it at
your dev database. Without it, database tests are skipped. Last full run: 218 passed (2026-11-15).
CI (`.github/workflows/ci.yml`) runs `ruff` and `pytest` against Postgres 16 on every PR and push to `main`.

## 4. Manager Q&A setup

Q&A turns on only when both Gemini and the read-only login are configured. It **never** falls back to `DATABASE_URL`.

1. `alembic upgrade head` creates the role `qa_reader` (no login) and the `qa_*` views.
2. As the database owner, enable the login once with a unique random password:
   ```sql
   ALTER ROLE qa_reader WITH LOGIN PASSWORD '<random password>';
   ```
   Generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
3. In `.env`: `DATABASE_URL_READONLY=postgresql+psycopg://qa_reader:<password>@<host>:5432/<db>`, the **same database** as `DATABASE_URL`.
4. Restart the worker. The log should say `Hỏi đáp (Q&A): bật`.
5. Try it without Zalo: `python scripts/qa_ask.py --tenant 1 "Kho tổng còn bao nhiêu cà phê kem béo?"`

Only staff with role `manager` can ask questions.
If a wrong URL or password is configured, the log still says the feature is on; every question then gets "not understood".

## 5. Common commands

| Task | Command |
|---|---|
| Run the API (auto reload) | `fastapi dev` |
| Run the worker | `python -m app.worker` |
| Pull messages from Zalo (dev) | `python scripts/zalo_poll.py` |
| Register the Zalo webhook | `python scripts/zalo_set_webhook.py` |
| Create an invite code | `python scripts/dev_db.py --invite "Name" [--role manager]` |
| Ask the Q&A agent from the CLI | `python scripts/qa_ask.py --tenant 1 "question"` |
| Test | `pytest` |
| Lint + fix / format | `ruff check . --fix` · `ruff format .` |
| Apply migrations | `alembic upgrade head` |
| New migration | `alembic revision -m "short_name"`, then write it by hand (do not autogenerate, see `database-design.md`) |

## 6. Environment variables

Set in `.env` (template: `.env.example`), read by `app/config.py`. **Never commit `.env`.**

| Variable | Purpose | Default / example |
|---|---|---|
| `DATABASE_URL` | Main app database (read and write) | `postgresql+psycopg://storagemate:storagemate@localhost:5432/storagemate` |
| `DATABASE_URL_READONLY` | `qa_reader` login for the Q&A agent. Empty = Q&A off | `postgresql+psycopg://qa_reader:***@localhost:5432/storagemate` |
| `TEST_DATABASE_URL` | Separate database for pytest, wiped every run. Empty = DB tests skipped | |
| `ZALO_BOT_TOKEN` | Zalo Bot API token (part of the URL, never logged) | |
| `ZALO_WEBHOOK_SECRET` | Checked on every webhook call | random, ≥ 32 characters |
| `PUBLIC_BASE_URL` | Public URL for the webhook | `https://<name>.ngrok-free.app` |
| `GEMINI_API_KEY` · `LLM_MODEL` | Gemini for the LLM parser and Q&A. Empty = both off | |
| `LLM_TIMEOUT_SECONDS` | Timeout for one Gemini call | `15` |
| `PENDING_TTL_MINUTES` | Time to reply `OK` to an LLM-read entry | `10` |
| `QA_TIMEOUT_SECONDS` · `QA_MAX_STEPS` | Limits for one Q&A question | `30` · `5` |
| `WORKER_POLL_SECONDS` | Worker sleep when the queue is empty | `1.0` |
| `INVITE_REUSABLE` | **Dev only**: invite codes can be reused. Never in production | `false` |
| `JWT_SECRET` · `DEV_AUTH_ENABLED` | Dashboard auth (login not built yet) | |
| `CORS_ORIGINS` | Dashboard domains, comma separated | `http://localhost:5173` |
| `HF_MODEL_REPO` · `NER_MODEL_PATH` | NER model (not used yet) | |
| `TZ` | Time zone | `Asia/Ho_Chi_Minh` |

Random string: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

## 7. Project layout

Domain-based packages (FastAPI "Bigger Applications" + fastapi-best-practices): each domain has `router` · `schemas`
· `models` · `service` (+ `dependencies`, `exceptions` when needed).

```
app/
├── main.py · api.py      # app, CORS, mounts /api and /webhooks
├── config.py · database.py · models.py · exceptions.py
├── worker.py             # worker process
├── channels/             # ⚡ Zalo webhook, adapters, Zalo client (only code that knows Zalo payloads)
├── messaging/            # ⚙️ queue (enqueue/claim), routing, bot replies
├── parser/               # ⚙️ regex → Gemini (structured output); NER not built yet
├── inventory/            # ledger, pending OK, stock + transactions API 🖥️
├── qa/                   # ⚙️ Q&A agent: loop, read-only tools, prompt
├── staff/                # staff, tenants, locations, invite codes
├── items/ · locations/ · dashboard/   # 🖥️ dashboard API
└── auth/ · labels/ · reports/ · chat/ # placeholders for later phases
alembic/versions/         # migrations (hand-written SQL)
scripts/                  # dev_db, zalo_poll, zalo_set_webhook, qa_ask, create_admin
tests/                    # pytest on a real Postgres
ml/                       # NER training pipeline (not deployed)
.claude/                  # specs, system design, ADRs
```

🖥️ called by the dashboard · ⚡ called by Zalo · ⚙️ worker only

**Rules:** the ledger is append-only · the webhook only enqueues · only regex results are written without `OK` ·
Q&A uses only the read-only login · exactly one worker · bot replies are in Vietnamese ·
never rename route functions (the dashboard generates its TypeScript client from `/api/openapi.json`).

## 8. Troubleshooting

| Problem | Fix |
|---|---|
| `requires a different Python: 3.14.x` | Recreate `.venv` with Python 3.11–3.13 (`py -0p` lists installed versions on Windows) |
| PowerShell blocks `.venv\Scripts\activate` | Run once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `fastapi` not recognized | Activate the venv first |
| `connection refused` to Postgres | Start Postgres and check `DATABASE_URL` |
| `password authentication failed for user "qa_reader"` | Run the `ALTER ROLE ... WITH LOGIN PASSWORD` step in [section 4](#4-manager-qa-setup) with the same password as `.env` |
| Manager questions get "not understood" | Check the worker log for `Hỏi đáp (Q&A): bật`, then [section 4](#4-manager-qa-setup). Gemini rate limits also cause this; ask again |
| Invite code rejected | Codes are single use; a new code revokes the old one. Create a new one with `scripts/dev_db.py --invite` |

## 9. Contributing

1. Branch from `main`: `git checkout -b feat/<short-name>`.
2. Write a spec in `.claude/specs/` before feature code ([template](.claude/specs/_TEMPLATE-spec-backend.md)).
3. `ruff check . --fix` and `pytest` must pass.
4. Commit as `feat: …`, `fix: …`, `docs: …`, then open a pull request to `main`; CI runs lint and tests.
