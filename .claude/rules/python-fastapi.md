---
paths:
  - "**/*.py"
---

# Python + FastAPI coding style (storagemate-service)

Extends `.claude/system-design/conventions.md`. When this file and generic advice disagree, this file wins —
it is tuned to how *this* repo is built (sync SQLAlchemy, domain folders, api + worker).

## 1. Tooling (enforced by CI)
- **ruff** is the only linter/formatter: `ruff check . --fix && ruff format .` must be clean before commit.
  Config lives in `pyproject.toml` (line-length 110, rules `E F I UP B`). Do not add black/isort/flake8.
- Target Python 3.11+: use `X | None`, `list[str]`, `collections.abc` types; no `typing.List/Optional/Union`.
- Type-hint every public function signature, including return type (`-> None` too).
- Imports: absolute from `app.` (`from app.config import settings`); no relative `..` imports; no wildcard.

## 2. Project layout (domain-first — fastapi-best-practices)
Each domain in `app/<domain>/` keeps the same file roles. Add a file only when it has content.

| File | Holds | Must NOT hold |
|------|-------|---------------|
| `router.py` | `APIRouter`, path ops, HTTP concerns (status codes, deps) | SQL, business rules |
| `schemas.py` | Pydantic request/response models | ORM models |
| `models.py` | SQLAlchemy models (inherit `app.models.Base`) | Pydantic |
| `service.py` | Business logic; takes `Session` + plain args, returns models/schemas | `Request`, `HTTPException` |
| `dependencies.py` | `Depends` callables (auth, load-or-404, validation against DB) | business logic |
| `exceptions.py` | Domain errors subclassing `app.exceptions.AppError` | — |

- Cross-domain imports go through the other domain's `service`/`schemas`, using the module name:
  `from app.items import service as items_service`. Never import another domain's `router`.
- `app/api.py` is the only place UI routers are mounted. Webhooks stay outside `/api`.
- Worker-only code (`messaging/`, `parser/`, `qa/`, `reports/jobs.py`) must not import FastAPI.

## 3. Routes
- **DB routes are `def`, not `async def`.** The DB layer is sync (`app/database.py`); FastAPI runs `def`
  routes in a threadpool. Use `async def` only when the body awaits something and does no blocking I/O.
  Never call `requests`, sync DB, or `time.sleep` inside `async def`.
- Dependencies via `Annotated` aliases defined once and reused:
  ```python
  DbSession = Annotated[Session, Depends(get_db)]
  CurrentAdmin = Annotated[Admin, Depends(get_current_user)]
  ```
- Always declare the response: return-type annotation or `response_model=`. Never return ORM objects or
  dicts that may leak fields (`password_hash`, tokens).
- Status codes via `fastapi.status` constants; `201` for create, `204` for no-body.
- Routers declare `prefix`, `tags`, and auth `dependencies=[...]` at router level (see `inventory/router.py`).
- Keep `operation_id` stable — the dashboard generates its TS client from `/api/openapi.json`.
  Renaming a route function = breaking change for the web repo.
- Use dependencies for "load or 404" and permission checks so handlers stay ~10 lines.

## 4. Pydantic v2
- Separate input and output models: `ItemCreate`, `ItemUpdate`, `ItemRead`. Never reuse one model for both.
- Output models reading ORM rows: `model_config = ConfigDict(from_attributes=True)`.
- Constrain at the boundary with `Field(gt=0, max_length=...)`, `Literal[...]`, `Enum` — not `if` checks in services.
- Use `model_dump(exclude_unset=True)` for PATCH.
- Quantities are `Decimal` (DB `NUMERIC`), never `float`. Times are timezone-aware `datetime` (DB `timestamptz`).
- LLM structured output is validated with a Pydantic model before it touches the ledger; on
  `ValidationError` treat it as "parser failed", never as partial data.

## 5. SQLAlchemy 2.0
- 2.0 style only: `Mapped[...]` + `mapped_column(...)`, `select()`, `session.scalars()/execute()`.
  No legacy `session.query()`.
- One session per request (`get_db`) / per job in the worker (`with SessionLocal() as s, s.begin():`).
  Services receive the session; they do not create engines or sessions.
- Commit boundary: one transaction per use case, owned by the caller (route or worker loop), not deep inside helpers.
- Raw SQL only via `text()` with bound params. Never f-string user/LLM input into SQL.
- Queue claim pattern is fixed: `SELECT ... FOR UPDATE SKIP LOCKED LIMIT n`. Dedup with
  `INSERT ... ON CONFLICT (channel, message_id) DO NOTHING`.
- **`inventory_log` is append-only.** No `UPDATE`/`DELETE` on it, anywhere. Cancel/fix = new row with `reverses_id`.
- Every schema change ships an Alembic migration (autogenerate, then read and fix it). Never edit an applied migration.
- Avoid N+1: `selectinload`/`joinedload` for list endpoints; paginate with `limit`/`offset` and a max page size.

## 6. Errors
- Services raise domain errors (`AppError` subclasses: `NotFoundError`, ...); the global handler in
  `app/exceptions.py` turns them into `{"code", "message"}`. Do not raise `HTTPException` from services.
- `HTTPException` is fine inside routers/dependencies for pure HTTP concerns (401/403).
- Never swallow exceptions. `except Exception` only at process boundaries (worker loop, job runner) and it must
  `logger.exception(...)` and mark the inbound message `failed` with the error.
- User-facing bot replies are Vietnamese, specific, and actionable ("Tồn đường chỉ còn 6 kg…"); never send tracebacks.

## 7. Config, secrets, logging
- All config through `app.config.settings` (pydantic-settings). No `os.getenv` scattered in code.
- Secrets live only in `.env`. Never hard-code, never log, never put in exception messages.
- Zalo token is part of the URL → keep `httpx` URL logging off and never log `request.url` of Zalo calls.
- Compare webhook secrets with `hmac.compare_digest`.
- Use `logging.getLogger(__name__)`; no `print()` in `app/` (scripts are fine).

## 8. External calls (httpx, LLM)
- One shared `httpx.Client`/`AsyncClient` per process with explicit `timeout=`; no client per call.
- Retries only where the Zalo error table says so (408/429/403 with backoff+jitter, max 3). 400/401/404: no retry.
- LLM/ONNX calls happen in the worker, never in the request path of `/webhooks/zalo`.

## 9. Tests (pytest)
- Mirror `app/` layout; name `test_<behaviour>()` in plain words.
- Use `fastapi.testclient.TestClient` + `app.dependency_overrides` for `get_db`/auth; don't monkeypatch internals.
- Parser changes must run against the golden set; synthetic data never goes into the golden set.
- No real Zalo/Gemini calls in tests — stub the client at the dependency/adapter boundary.

## 10. Style details
- Functions < ~40 lines, one job each; early returns over nesting.
- Named constants for business limits (`INVITE_TTL = timedelta(hours=24)`, `REVERSE_WINDOW = timedelta(minutes=30)`).
- Docstrings: one line saying *why*, in the repo's existing language (Vietnamese is fine). No restating the signature.
- Prefer stdlib and already-installed deps; adding a dependency needs a reason in the PR.
