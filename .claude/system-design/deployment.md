# Deployment
> last-updated: 2026-11-02 · Phase 5 target; source: `docs/storagemate-proposal-plan-v2.md` §Deploy

## Environments
| Env | URL | Hosting | Database | Notes |
|-----|-----|---------|----------|-------|
| local dev | localhost:8000 | `fastapi dev` + `python -m app.worker`, or `docker compose up --build` | compose `postgres:16` | Zalo via polling (`scripts/zalo_poll.py`) |
| demo ("prod") | `PUBLIC_BASE_URL` (ngrok fixed dev domain) | Docker Compose on Windows laptop (Docker Desktop + WSL 2) | same compose, `pgdata` volume | Up only during test/demo → $0 hosting |
| dashboard | `*.vercel.app` | Vercel (separate web repo) | — | Calls API through ngrok |

Containers: `api`, `worker` (same image, **exactly 1 worker**), `postgres`. NER `.onnx` mounted read-only from `./models`.

## CI/CD
- PR → GitHub-hosted runner: `ruff check`, `ruff format --check`, `pytest` incl. parser golden set (`.github/workflows/ci.yml`).
- Push to `main` → self-hosted runner on the laptop: `docker compose up -d --build` (only when laptop is on).
  `deploy-api.yml` <!-- not written yet -->. Runs **only on push to main, never on `pull_request`**; repo stays private.

## Deploy steps
1. Merge to `main` → runner rebuilds and restarts containers.
2. Migrations: `alembic upgrade head` <!-- unknown: run in api entrypoint or manual step — decide when first migration lands -->.
3. Domain changed? rerun `scripts/zalo_set_webhook.py`.

## Rollback
Redeploy previous commit (`git revert` on main → runner rebuilds). Never edit applied migrations; write a new one.
Ledger is append-only, so data fixes are reversing rows, not restores.

## Backups & secrets
- `pg_dump` periodically from the `postgres` container. <!-- unknown: schedule -->
- Secrets only in `.env` on the laptop (gitignored). Rotate `ZALO_BOT_TOKEN` via Zalo Bot Creator if leaked.

## Why not free cloud
Render free: 512 MB, sleeps after 15 min, Postgres expires in 30 days. HF Docker Spaces now paid. OrbStack is macOS-only.
