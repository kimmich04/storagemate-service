# Conventions & Invariants
> last-updated: 2026-11-01

The rules that must always hold. CLAUDE.md points here.
"Code discipline" below ships with the scaffold and applies as-is; every section
after it is a placeholder for *this* project to fill in.

## Code discipline
> Full behavioral rules: the **karpathy-guidelines** skill. This section is the enforced subset.

### Think before coding
- State assumptions explicitly. If uncertain, ask — do not guess and proceed.
- If multiple interpretations exist, present them. Do not silently pick one.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop and name what is confusing.

### KISS — Keep It Simple, Stupid
Write the simplest code that satisfies the requirement. Nothing more.

- If 200 lines could be 50, rewrite it.
- No speculative abstractions, no configurability that wasn't asked for.
- No error handling for impossible scenarios.
- No code duplication — extract shared logic rather than copying.
- The simplest solution that passes all success criteria is the correct one.

### SOLID
Apply when the need is proven, not preemptively. KISS wins ties.

| Principle | Rule | Example in this project |
| --- | --- | --- |
| **S** — Single Responsibility | One module, one reason to change. | A file that both fetches data and renders it gets split; see the layering in `overview.md` and `directory-map.md`. |
| **O** — Open/Closed | Extend via new code, not by editing working code. | Add a new handler/strategy file instead of adding another `if` branch to a dispatcher. |
| **L** — Liskov Substitution | Any implementation must be usable wherever its interface is expected. | A swapped adapter (mock vs. real client) must not require callers to change. |
| **I** — Interface Segregation | Small, focused interfaces over one fat one. | Consumers depend on the narrow contract they use, not on a god-type re-exported everywhere. |
| **D** — Dependency Inversion | Depend on abstractions; inject concretions at the edge. | Business logic takes a client/repo as a parameter; wiring happens at the entrypoint — see "Code style" below. |

### Surgical changes
- Touch only what the spec requires. Every changed line traces to the request.
- Do not "improve" adjacent code, comments, or formatting.
- Match existing style, even if you'd do it differently.
- Clean up orphans **your** change created (unused imports/vars/functions).
- Pre-existing dead code: mention it, do not delete it.

### Goal-driven execution
Turn the task into verifiable criteria before writing code:
- "Add validation" → "write tests for invalid inputs, then make them pass".
- "Fix the bug" → "write a test that reproduces it, then make it pass".
- "Refactor X" → "tests pass before and after".

For multi-step work, state the plan as `step → verify` pairs and loop until each check passes.

## Naming
- Python: `snake_case` modules/functions, `PascalCase` classes, `UPPER_SNAKE` constants. Schemas: `<Entity>Create/Update/Read`.
- DB: plural `snake_case` tables (`inventory_log`, `invite_codes`), `<table>_id` FKs; constraint names come from `app/models.py` NAMING_CONVENTION.
- Branches: `feat/<short>`, `fix/<short>`. Alembic messages: short snake_case.

## Error handling
Domain errors subclass `app.exceptions.AppError` → JSON `{"code","message"}`. Worker catches at the loop boundary,
logs, and marks `inbound_messages.status = failed` with `error`. Detail: `.claude/rules/python-fastapi.md` §6.

## Testing strategy
pytest + TestClient with `dependency_overrides`. Parser measured on the real-human golden set (never synthetic).
No real Zalo/Gemini calls in tests. CI (`.github/workflows/ci.yml`) runs `ruff check` + `pytest` on every PR.

## Security invariants
- Webhook: `X-Bot-Api-Secret-Token` checked with `hmac.compare_digest`; mismatch → 403, nothing stored.
- Identity = Zalo `from.id`/`chat.id` linked via one-time invite code. Never trust `display_name`.
- Zalo bot token is in the request URL → never log URLs of Zalo calls.
- Q&A agent uses `DATABASE_URL_READONLY` (SELECT on business views only, 5 s timeout, ≤200 rows).
- `/api/*` requires admin JWT. Secrets only in `.env`.

## Git & commits
Conventional Commits (`feat:`, `fix:`, `docs:` …). Branch from `main`, PR into `main`; `ruff` + `pytest` must pass.

## Code style
Python/FastAPI rules: `.claude/rules/python-fastapi.md` (ruff, typing, domain layout, sync DB routes, Pydantic v2, SQLAlchemy 2.0).
