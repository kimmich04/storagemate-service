# Data Flow
> last-updated: 2026-11-02 · source: `docs/storagemate-proposal-plan-v2.md` §Luồng hệ thống

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
