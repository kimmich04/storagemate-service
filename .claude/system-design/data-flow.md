# Data Flow
> last-updated: 2026-11-09 · source: `docs/storagemate-proposal-plan-v2.md` §Luồng hệ thống

The runtime story. 8 flows: bot setup (once), staff linking, message processing (main), confirm/cancel,
manager Q&A, scheduled reports, dashboard, flywheel. Business limits are named constants in code.

## 1. Bot setup (once, manual)
- Create bot in Zalo app (Zalo Bot Manager → Zalo Bot Creator, name starts with "Bot"). Token → `.env` `ZALO_BOT_TOKEN`.
- `getMe` to verify. Local dev: `scripts/zalo_poll.py` (`getUpdates`, no public URL).
- Demo/prod: ngrok fixed domain → `scripts/zalo_set_webhook.py` (`setWebhook(url, secret_token)`).
- **Polling and webhook are mutually exclusive**: after `setWebhook`, `getUpdates` silently stops; `deleteWebhook` to go back.

## 2. Staff linking (invite code)
Zalo payload has no phone number → identity = `from.id` / `chat.id`, linked to `staff` by invite code.
```mermaid
sequenceDiagram
  actor A as Admin
  actor S as Staff
  participant API as api
  participant W as worker
  participant DB as postgres
  A->>API: POST /api/staff/{id}/invite
  API->>DB: invite_codes (6 chars, 1-use, TTL 24h)
  API-->>A: code + bot deeplink/QR
  S->>W: (via Zalo) "K7P2Q9"
  W->>DB: chat_id unlinked → check code
  alt valid
    W->>DB: staff.zalo_user_id, zalo_chat_id, linked_at; code.used_at
    W-->>S: greeting + syntax
  else invalid/expired
    W-->>S: reject, write nothing (>5 fails / 15 min → lock chat_id)
  end
```
**Phase 1 implementation** (spec `2026-11-06-phase1-invite-code-spec.md`, `app/messaging/queue._handle_unlinked` +
`app/staff/service.redeem_invite`):
- No dashboard yet → manager's step is `python scripts/dev_db.py --invite "Tên" [--role manager]` (creates the staff row
  if the name is new, revokes older unused codes, prints the code). The manager sends the code to the staff member.
- Unlinked chat: text → strip spaces + upper-case; not 6 × `A-Z0-9` → "gửi mã mời" reply, `ignored` / `unlinked`.
  Code valid (unused, not revoked, not expired, staff active) → link chat + `from.id`, `used_at`, greeting + syntax,
  `done` / `invite_ok`. Anything else → one identical rejection, `done` / `invite_failed`.
- Chat / Zalo user held by an **inactive** staff row → moved to the new row; held by an **active** row → rejected.
- A linked chat that sends a code-like text is treated as normal text. No lockout yet: Phase 4 counts
  `route = 'invite_failed'` per `chat_id` in 15 min (no extra column).

## 3. Message processing (main flow)
```mermaid
sequenceDiagram
  participant Z as Zalo
  participant API as api /webhooks/zalo
  participant DB as postgres
  participant W as worker
  Z->>API: POST + X-Bot-Api-Secret-Token
  API->>API: hmac.compare_digest (mismatch → 403, not stored)
  API->>DB: adapter → InboundMessage; INSERT … ON CONFLICT (channel, message_id) DO NOTHING
  API-->>Z: 200 immediately
  W->>DB: SELECT … FOR UPDATE SKIP LOCKED
  W->>Z: sendChatAction(typing)
  W->>W: identify by chat_id → router → parser cascade → validate
  alt regex parse
    W->>DB: INSERT inventory_log
  else NER/LLM parse
    W->>DB: INSERT pending_actions (ask OK/Sai)
  end
  W->>Z: sendMessage
  W->>DB: inbound status done/failed(+error); outbound_messages
```
Router order: unlinked → invite flow · non-text event → "please type text" · system command
(`OK` `Sai` `Hủy` `Tồn …` `Hướng dẫn` `Báo cáo`) · `Nhập`/`Xuất` or parser detects stock command → stock branch ·
else manager → Q&A, staff → syntax help.

Validate: item in catalog (aliases too), unit valid + convertible, qty > 0, OUT not beyond stock,
`event_time` not in future and ≤ 7 days old. Missing time/date → received time.

## 3a. Phase 1 message path (what runs today — spec 2026-11-06-phase1-db-ledger)
Webhook and `scripts/zalo_poll.py` only **enqueue**; `python -m app.worker` (exactly one) answers.
```mermaid
sequenceDiagram
  participant Z as Zalo
  participant R as router.zalo_webhook / zalo_poll
  participant DB as postgres
  participant W as worker → queue.process_next
  participant D as dispatcher.handle
  participant L as ledger.record
  Z->>R: POST /webhooks/zalo + secret (or getUpdates)
  R->>R: verify secret (403) · save_sample · parse_update
  R->>DB: inbox.enqueue: INSERT … ON CONFLICT (channel, external_id) DO NOTHING
  R-->>Z: 200
  W->>DB: BEGIN; claim 1 pending FOR UPDATE SKIP LOCKED (status=processing)
  W->>Z: sendChatAction(typing)
  W->>DB: staff by zalo_chat_id — none/inactive → status=ignored, route=unlinked
  W->>D: handle(msg, now, PendingStore) → Outcome(replies, route, phieu?, origin?)
  D-->>W: phiếu chốt (no duplicate group left) or A/B/C question
  W->>L: phiếu chốt → INSERT inventory_log per line (regex, base unit, stock check)
  L-->>W: LedgerResult(written, total, skipped+reason, date_error)
  W->>DB: status=done, route; COMMIT
  W->>Z: summary + "✅ Đã ghi x/y" + lines NOT written (after COMMIT only)
```
- One transaction per message; crash → rollback → message back to `pending`. Handler error → rollback, new txn
  `status=failed`, `error`, `attempts+1`, staff gets "⚠️ Bot gặp lỗi…". Send failure after commit is only logged.
- Lines are written **one by one**: unknown/ambiguous item, unconverted unit, unreadable line, OUT beyond stock →
  skipped and listed in the reply ("CHƯA có trong sổ và dashboard"); staff retypes them as a new phiếu.
  Bundle ("bộ") → one row per component; one component short → whole line skipped.
- Date of the whole phiếu in the future or > 7 days old → nothing written.
- Every row: `location_id` = staff's default location (kho tổng); the other side → `counterpart_location_id`
  (no match → NULL). Only kho tổng stock is tracked.
- `route` on `inbound_messages`: `phieu` · `phieu_partial` · `phieu_rejected` · `phieu_waiting` (A/B/C asked) ·
  `phieu_answer` (the "a"/"c" reply; ledger rows point to the **original** phiếu message) · `unlinked` · `other`.
  Phase 2 re-parses `text` of `phieu_partial` rows to send skipped lines to NER/LLM.
- **LLM fallback (Phase 2a, regex → LLM; NER chưa có).** Dispatcher sets `Outcome.wants_llm` when `parse_phieu` returns
  `None` or finds a header but **zero lines** (free text such as "hôm qua nhập 10 hộp cà phê"). Worker then calls
  `parser/llm.py` (`await llm.parse`, Gemini structured output → `Phieu`). Read → row in `pending_actions`
  (`parser_source='llm'`, TTL `PENDING_TTL_MINUTES`) + summary asking **OK/Sai**; **nothing is written yet**
  (route `llm_waiting`). Not read / LLM off / error / timeout → the regex reply is sent (`unknown` or "Chưa có dòng hàng nào").
- **OK/Sai** are checked in `queue._answer_pending` *before* the dispatcher: `OK` → `ledger.record(source='llm')` + pending
  `confirmed` (original message route = ledger result, the `OK` message = `phieu_answer`); `Sai` → `rejected`
  (`llm_rejected`); after TTL → `expired` (`llm_expired`); any other message expires the pending and is handled normally.
  `OK`/`Sai` with nothing waiting → "không có phiếu nào đang chờ" (no LLM call).
- LLM phieu goes through the same `catalog.resolve` + `ledger.record` checks (unknown item, unit, stock, ≤ 7 days); duplicate
  lines (A/B/C) are not asked for LLM phiếu — staff sees them in the summary and answers `Sai`. The LLM call happens while the
  inbound row is locked (one worker, `LLM_TIMEOUT_SECONDS`, no retry).
- `PendingStore` (A/B/C, 10 min) still lives in worker RAM — fine with one worker, lost on restart.
- Zalo does not redeliver → messages sent while the server is down are lost (integrations.md).

## 4. Confirm / fix / cancel
- `OK` → pending → `inventory_log`; sample → `training_samples` (verified = true).
- `Sai` → drop pending, sample flagged for manager review, bot re-prompts syntax.
- Pending unanswered 10 min → auto-cancel.
- `Hủy` → reversing row (`reverses_id`, flipped action) for sender's latest row, within 30 min.
  After that only manager via dashboard — still a reversing row. **Never UPDATE/DELETE the ledger.**
- No buttons in Bot API → confirmation is typed text.

## 5. Manager Q&A
- Manager role only (staff → help text).
- LLM tool calling over fixed tools: `get_stock(item)`, `get_movements(item, from, to, action)`,
  `top_items(period)`, `staff_activity(period)`; else LangChain SQL agent fallback.
- Runs as `qa_reader` role: SELECT on business views only (no `admins`, `staff`), `statement_timeout` 5 s, ≤ 200 rows.
- Reply ≤ 2,000 chars (sendMessage limit) → split or send dashboard link.

## 6. Scheduled reports
- APScheduler inside the (single) worker, `Asia/Ho_Chi_Minh`: daily 21:30, monthly 07:00 on day 1;
  `misfire_grace_time` + `coalesce` so a sleeping laptop catches up.
- `sendMessage` to managers: IN/OUT in period, below `min_stock`, staff with many syntax errors + dashboard link.
- Proactive send after long silence is **unverified** (Phase 0) → fallback: `Báo cáo` command / dashboard.

## 7. Dashboard / web chat
- JWT login; pages Login, Stock, Transactions, Staff, Items, Labels, Chat, Reports (separate web repo).
- Web chat: `POST /api/chat/messages` → web adapter → **same queue + worker** as Zalo; UI polls
  `GET /api/chat/messages` every 1–2 s.

## 8. Data flywheel
- OK-confirmed messages + manager edits → `training_samples`. Raw LLM output is never a label until a human confirms.
- Weekly-ish: export BIO → retrain on Colab → compare F1 on golden set → better model to HF Hub → worker loads on restart.
- No realtime weight updates (one bad typist could poison the model).
