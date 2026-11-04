# API Contracts
> last-updated: 2026-11-04 · source: `docs/storagemate-proposal-plan-v2.md` §API sử dụng

Source of truth for the internal API = FastAPI OpenAPI (`/api/openapi.json`); the dashboard generates its TS
client from it, so `operation_id` (`<tag>-<func>`) must stay stable. This doc is the human summary.

## Auth model
- `/api/*`: admin JWT (OAuth2 password flow, PyJWT, pwdlib argon2). One admin via `scripts/create_admin.py`, no signup.
- `/webhooks/zalo`: `X-Bot-Api-Secret-Token` header vs `ZALO_WEBHOOK_SECRET` (`hmac.compare_digest`, ≥ 32 chars).
- Bot users: no token — identity = linked `chat_id` + `staff.role` (see data-flow §2).

## Conventions
- No version prefix; UI routes under `/api`, webhooks outside it.
- Error shape: `{"code", "message"}` from `AppError` handler (`app/exceptions.py`).
- Dashboard calls go through ngrok → must send `ngrok-skip-browser-warning`; CORS allows Vercel domain + that header.
- Pagination: `limit`/`offset` with a max page size.

## Internal endpoints
| Method | Path | Caller | Purpose |
|--------|------|--------|---------|
| POST | `/webhooks/zalo` | Zalo | Verify secret, enqueue, 200 (Phase 0: BackgroundTasks, see below) |
| GET | `/health` | Compose, CI | DB, queue, `getMe` |
| POST | `/api/auth/login` | Dashboard | Password → JWT |
| GET | `/api/stock` | Dashboard | `current_stock` view |
| GET | `/api/transactions` | Dashboard | Ledger history, filter item/staff/date |
| POST | `/api/transactions/{id}/reverse` | Dashboard | Reversing row |
| GET/POST/PATCH | `/api/items` | Dashboard | Catalog, aliases, units, `min_stock` |
| GET/POST/PATCH | `/api/staff` | Dashboard | Staff, role, lock/unlock |
| POST | `/api/staff/{id}/invite` | Dashboard | Invite code + bot deeplink/QR |
| GET · PATCH | `/api/labels` · `/api/labels/{id}` | Dashboard | Label review (flywheel) |
| GET | `/api/reports/daily` · `/api/reports/monthly` | Dashboard | Period reports |
| POST · GET | `/api/chat/messages` | Web chat | Send into pipeline · poll replies |

## Zalo Bot API (outbound)
`POST https://bot-api.zaloplatforms.com/bot{BOT_TOKEN}/{method}`, JSON body. **Token is in the URL → never log URLs.**

| Method | Key params | Used for |
|--------|-----------|----------|
| getMe | — | Startup + `/health` |
| setWebhook | `url` (HTTPS), `secret_token` (8–256) | `scripts/zalo_set_webhook.py`, rerun on domain change |
| deleteWebhook / getWebhookInfo / testWebhook | — | Back to polling / debug (testWebhook has daily quota) |
| getUpdates | `timeout` (30 s) | Local polling; ≤ 1 update per call |
| sendMessage | `chat_id`, `text` (1–2,000), `parse_mode`? | All replies, reports |
| sendChatAction | `chat_id`, `action=typing` | While NER/LLM runs |
| sendPhoto | `chat_id`, `photo` URL, `caption` | Optional report charts |

## Zalo error handling
| Code | Meaning | Action |
|------|---------|--------|
| 400 | Bad path/method; also `deleteWebhook` when no webhook is set | Code bug — log + alert, no retry |
| 401 | Token invalid/expired | Stop sending, alert admin, log |
| 403 | Zalo server error | Retry with backoff, max 3 |
| 404 | Invalid request; also `getWebhookInfo` when no webhook is set | Log, no retry |
| 408 | Timeout (common on getUpdates) | Polling: call again; send: retry |
| 429 | Rate limited | Exponential backoff + jitter |

Implemented in `app/channels/zalo_client.py` (`ZaloClient._call`): retries 403/408/429 up to 3× with
`0.5·2ⁿ` s + jitter; `getUpdates` 408 → `None` (no retry); token redacted to `***` in every error.

## Inbound webhook (Zalo → us)
`POST /webhooks/zalo` — `app/channels/router.py`.

| Case | Response |
|------|----------|
| `X-Bot-Api-Secret-Token` missing/wrong, or `ZALO_WEBHOOK_SECRET` empty | **403**, body not read (dependency runs first) |
| Valid secret, readable event | **200** `{"message":"Success"}`, then `process()` in BackgroundTasks (Phase 0) |
| Valid secret, unreadable event (e.g. `webhook.test`) | **200** `{"message":"Success"}`, warning logged, nothing sent |

Every accepted payload is appended raw to `data/zalo_samples/YYYY-MM-DD.jsonl` (gitignored, Phase 0 only).

Webhook body (verified live 2026-11-04 — **no** `{ok, result}` wrapper; `getUpdates` wraps one event in `{ok, result}`):
```json
{"event_name": "message.text.received",
 "message": {"message_id": "…", "date": 1793776841137, "message_type": "CHAT_TEXT",
   "from": {"id": "…", "display_name": "Lan", "is_bot": false},
   "chat": {"id": "…", "chat_type": "PRIVATE"}, "text": "menu"}}
```
`date` is epoch **milliseconds**. Events: `message.{text,image,sticker,voice,unsupported}.received`, plus
`webhook.test` sent by `setWebhook` verification. Store raw payload (jsonb, Phase 1). Never identify by
`display_name`. <!-- unverified: image field names (adapter assumes `photo_url` + `caption`) -->
