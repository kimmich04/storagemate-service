# Deployment
> last-updated: 2026-11-15 · Phase 5 target; source: `docs/storagemate-proposal-plan-v2.md` §Deploy

## Environments
| Env | URL | Hosting | Database | Notes |
|-----|-----|---------|----------|-------|
| local dev | localhost:8000 | `fastapi dev` + `python -m app.worker`, or `docker compose up --build` | compose `postgres:16` | Zalo via polling (`scripts/zalo_poll.py`) |
| demo ("prod") | `PUBLIC_BASE_URL` (ngrok fixed dev domain) | Docker Compose on Windows laptop (Docker Desktop + WSL 2) | same compose, `pgdata` volume | Up only during test/demo → $0 hosting |
| dashboard | `*.vercel.app` | Vercel (separate web repo) | — | Calls API through ngrok |

Containers: `api`, `worker` (same image, **exactly 1 worker**), `postgres`. NER `.onnx` mounted read-only from `./models`.

## CI/CD
- PR → GitHub-hosted runner: `ruff check`, `pytest` incl. parser golden set (`.github/workflows/ci.yml`).
  CI starts a `postgres:16` service and sets `TEST_DATABASE_URL`; DB tests downgrade/upgrade the schema each run.
  Locally without `TEST_DATABASE_URL` the DB tests are skipped.
- New dev machine (owner: PostgreSQL 16 on Windows, no Docker for the dev DB): create role/DB → `alembic upgrade head`
  → `psql -f seed_t10_2026.sql` → `python scripts/dev_db.py --map-codes` → `--link-staff` → (optional) `--fake-moves`.
  Exact PowerShell commands + Zalo test cases: spec `2026-11-06-phase1-db-ledger-spec.md` §2. Production go-live must pick a fresh opening date and never run `--fake-moves`.
- Push to `main` → self-hosted runner on the laptop: `docker compose up -d --build` (only when laptop is on).
  `deploy-api.yml` <!-- not written yet -->. Runs **only on push to main, never on `pull_request`**; repo stays private.

## Deploy steps
1. Merge to `main` → runner rebuilds and restarts containers.
2. Migrations: `alembic upgrade head` <!-- unknown: run in api entrypoint or manual step — decide when first migration lands -->.
3. Domain changed? rerun `scripts/zalo_set_webhook.py`.
4. Once per database, after migration `0003_qa_reader`: `ALTER ROLE qa_reader WITH LOGIN PASSWORD '<random ≥ 32>'`,
   then set `DATABASE_URL_READONLY` in `.env` (Supabase pooler user: `qa_reader.<project-ref>` — unverified).
   Without it the worker logs "Hỏi đáp (Q&A): tắt" and everything else runs. The role needs `CREATEROLE` on the migration
   user; on Supabase (not superuser) this is unverified — fallback: create the role in the SQL editor, rerun the migration.
5. Manager on Zalo: `UPDATE staff SET role = 'manager' WHERE …` (no Staff page yet).

## Rollback
Redeploy previous commit (`git revert` on main → runner rebuilds). Never edit applied migrations; write a new one.
Ledger is append-only, so data fixes are reversing rows, not restores.

## Backups & secrets
- `pg_dump` periodically from the `postgres` container. <!-- unknown: schedule -->
- Secrets only in `.env` on the laptop (gitignored). Rotate `ZALO_BOT_TOKEN` via Zalo Bot Creator if leaked.
  `qa_reader` password lives only in `DATABASE_URL_READONLY`; rotate with `ALTER ROLE qa_reader PASSWORD …`.

## Why not free cloud
Render free: 512 MB, sleeps after 15 min, Postgres expires in 30 days. HF Docker Spaces now paid. OrbStack is macOS-only.
