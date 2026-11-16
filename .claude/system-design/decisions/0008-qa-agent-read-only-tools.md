# 0008. Manager Q&A as a tool-calling agent on a separate read-only login
> Status: Accepted
> Date: 2026-11-15

## Context
Managers want to ask stock questions in plain Vietnamese on Zalo ("kho tổng còn bao nhiêu trứng", "tháng 10 xuất
nhiều nhất món gì"). Answering needs several lookups chosen at runtime (find the item, then its stock or history),
which a fixed pipeline cannot do. The proposal requires Q&A to run on a read-only DB role. The LLM must never be able
to change the ledger or see another tenant, even if a message tries to steer it (prompt injection).
The project now targets production quality, not the hackathon deadline.

## Decision
- We will run Q&A as an **agent loop we write ourselves** (`app/qa/service.py`): Gemini `bind_tools` → run the
  requested tools → feed results back → repeat, capped by `QA_MAX_STEPS` and `QA_TIMEOUT_SECONDS`.
- Tools are **pre-written, read-only, parameterised SQL** over `qa_*` views; Gemini fills only Pydantic-validated
  arguments. Tenant, date and connection come from code.
- Q&A connects with its **own login `qa_reader`** (`DATABASE_URL_READONLY`): SELECT on 4 views only,
  `default_transaction_read_only`, `statement_timeout 5s`. Missing URL → Q&A off; never fall back to the app login.
- Views filter `tenant_id` by `app.tenant_id` themselves (owner rights, fail closed when unset).
- Message classification is folded into the existing LLM parser call (`intent` = phieu | cau_hoi | khac) instead
  of a separate classifier call. Permission is checked on `staff.role`, not on the LLM's intent.

## Alternatives considered
- `langchain.agents.create_agent` — works, but adds a layer whose step limits and message handling are harder to
  pin down in tests; our loop is ~30 lines and is tested with a scripted fake model.
- `SET LOCAL ROLE qa_reader` on the app connection — no extra secret, but safety depends on every code path
  remembering to switch role, and LLM-written SQL could `RESET ROLE`. Kept only for tests (no password in CI).
- SQL agent (LLM writes SQL) as the main path — flexible but hard to verify; deferred to a fallback spec, which will
  require this separate login anyway.
- Separate classifier call before the parser — same number of calls for questions, one extra call for every
  free-text phiếu.

## Consequences
- The worst a hostile or confused message can do is get a wrong answer about its own tenant's data.
- One more secret to manage (`qa_reader` password) and one more step per database (`ALTER ROLE … LOGIN PASSWORD`).
- A manager question costs 1 parser call + 1–5 agent calls; the free Gemini tier hits rate limits quickly.
- Follow-ups: SQL agent fallback, conversation memory, `Tồn <tên>` shortcut, a golden question set run in CI.
