# storagemate-service — Claude Code guide

> This file is ALWAYS loaded into context. Keep it SHORT. It is a map and a set of
> hard rules — the detail lives in the folders it points to. Do not paste architecture
> here; point to `.claude/system-design/`.

## 1. What this is
Backend of Storagemate: a Zalo Bot AI agent that turns F&B staff messages ("Nhập 50 kg bột mì 14h 28/10")
into an append-only inventory ledger, real-time stock, manager Q&A and daily/monthly reports.
FastAPI `api` + `worker` (same image) + PostgreSQL 16. Dashboard (React + Vite) is a **separate web repo**.
Scope source of truth: `docs/storagemate-proposal-plan-v2.md` (Markdown of *Storagemate-Proposal-Plan v2*, 2026-11-01);
agent summary in `system-design/overview.md`. Proposal and code disagree → ask, don't silently pick one.

## 2. Read order at the start of a task
1. Read `.claude/system-design/README.md` (index + freshness) and open only the docs the task touches.
2. For structural questions ("who calls X", "what breaks if I change Y"), **query the graph, do not grep the repo**: `graphify query "..."` (see `.claude/memory/README.md`).
3. Check `.claude/specs/STATUS.md` for the active spec and its roadmap phase (0–6). Work only inside the current phase.

## 3. Model policy
- **Opus** → brainstorm, spec, plan, architecture decisions.
- **Sonnet** → implementation, refactors, tests, routine edits.

## 4. Workflow gates (do not skip)
`brainstorm → spec → plan → implement`. Never write feature code before a spec exists (`/new-spec <phase>`).
- Which skill/plugin at each gate: `.claude/skills/ROUTER.md`.
- Which MCP to reach for: `.claude/mcp/ROUTER.md`.

## 5. Spec + system-design discipline (this keeps the docs alive)
- Every task lives in `.claude/specs/` and is tracked in `.claude/specs/STATUS.md`.
- **Before you mark a task ✅**: if the change touched architecture, schema, API, or a decision,
  update the matching file in `.claude/system-design/` and bump its `last-updated` in the README.
  A task is not done until the docs that describe it are true again.

## 6. Cost discipline
- Default to Sonnet; keep context lean; clear between unrelated tasks.
- Token/cost visibility via **ccusage** (`npx ccusage@latest`) — wired into the statusline in `settings.json`.

## 7. Hard rules
- Follow `.claude/system-design/conventions.md` — code discipline (KISS, SOLID, surgical changes),
  naming, errors, tests, security. Read it before writing code.
- Do not delete or rewrite decisions in `.claude/system-design/decisions/` without a new ADR.
- Make the smallest change that satisfies the spec (see the karpathy-guidelines skill).

## 8. Stack
<!-- STACK-SNIPPET-START -->
**Python 3.11–3.13 · FastAPI · Pydantic v2 · SQLAlchemy 2.0 (sync, psycopg 3) · Alembic · httpx · APScheduler 3.x · ONNX Runtime · LangChain + Gemini (LLM provider final in Phase 2).**
Proposal names Python 3.12 + uv; repo currently uses pip + `requires-python >=3.11,<3.14` — `uv pip install -e ".[dev]"` also works.
Coding rules: `.claude/rules/python-fastapi.md` (auto-loaded for `*.py`).

| Task | Command |
|------|---------|
| Install (dev) | `pip install -e ".[dev]"` |
| Run API | `fastapi dev` |
| Run worker | `python -m app.worker` |
| Lint / format | `ruff check . --fix` · `ruff format .` |
| Test | `pytest` |
| Migration | `alembic revision --autogenerate -m "..."` → `alembic upgrade head` |
| Full stack | `docker compose up --build` |

Non-negotiables: ledger `inventory_log` is append-only (fix = reversing row); webhook returns 200 fast and
only enqueues; never log the Zalo token (it's in the URL); Q&A runs on the read-only DB role; only regex parses
write directly — NER/LLM parses need the sender's `OK`; exactly one worker; never read `.env`; bot replies in Vietnamese.
<!-- STACK-SNIPPET-END -->
