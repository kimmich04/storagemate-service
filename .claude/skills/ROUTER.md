# Skills ROUTER — storagemate-service

Claude: match the situation to a row before starting. Skills are invoked by name. Generic kits that don't fit this
stack (Next.js, Spring, Stripe, CMS, email, Drizzle) are intentionally left out.

## Gate → skill (the harness)
| Situation | Use | Note |
|-----------|-----|------|
| New feature / behaviour change | **superpowers:brainstorming** FIRST | No code before a spec in `.claude/specs/` |
| Spec → steps | **superpowers:writing-plans** | Use `/new-spec` to start the spec file |
| Writing/refactoring code | **andrej-karpathy-skills:karpathy-guidelines** + `rules/python-fastapi.md` | Smallest change |
| Bug fix / new logic | **superpowers:test-driven-development** | pytest; parser changes run the golden set |
| Bug / stack trace / "worked yesterday" | **superpowers:systematic-debugging** | |
| Locking a choice (LLM provider, NER split…) | ADR in `system-design/decisions/` | `engineering:architecture` for the tradeoff |
| Before merge | **code-review**, then **security-review** if auth/webhook/Q&A SQL touched | |
| After implementing | **simplify** | Quality only |
| Codebase structure questions | **graphify** — `.claude/memory/README.md` | Query, don't grep |

## Domain → skill
| Area in this repo | Skill | Use when |
|-------------------|-------|----------|
| Routers, deps, Pydantic, settings | **fastapi** | Any `app/<domain>/router.py`, `schemas.py` |
| Schema, migrations, views, roles, SKIP LOCKED | **postgresql**, **data-modeling**, **migrate** | `models.py`, `alembic/`, `current_stock`, `qa_reader` |
| `/webhooks/zalo`, secret verify, dedup | **webhooks**, **idempotency** | `app/channels/` |
| Zalo/LLM client retries, backoff | **error-handling**, **rate-limiting** | `zalo_client.py`, `parser/llm.py` |
| Reports scheduler | **cron-jobs** | `app/reports/jobs.py` (APScheduler 3.x) |
| LLM structured output, Q&A tool calling | **ai-function-calling**, **prompt-engineering** | `app/parser/llm.py`, `app/qa/` |
| Admin JWT, pwdlib | **authentication**, **security-toolkit** | `app/auth/` (Phase 4) |
| NER training, ONNX export, eval | **ml-ops** | `ml/` (Colab, not deployed) |
| Compose, Dockerfile, GitHub Actions, self-hosted runner | **devops-kit** | Phase 5 |
| Tests (golden set, webhook, parser) | **testing-toolkit** | `tests/` |
| Bot reply copy (Vietnamese) | **anthropic-skills:vietnamese** | Replies must be specific + actionable |
| Diagrams in system-design | **mermaid** | |
| Docs / README / changelog | **docs-kit** | Keep `docs/` proposal as scope source |

## Library docs
Always pull version-correct docs via **context7** before writing code against: FastAPI, SQLAlchemy 2.0,
Pydantic v2, Alembic, httpx, APScheduler **3.x** (not 4), LangChain, google-genai, Transformers, Optimum, ONNX Runtime.

## Project commands (`.claude/commands/`)
| Command | Does |
|---------|------|
| `/new-spec <phase or feature>` | Creates a spec from `_TEMPLATE-spec.md`, prefilled from the proposal, and adds it to STATUS.md |
