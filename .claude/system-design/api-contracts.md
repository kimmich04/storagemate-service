# API Contracts
> last-updated: 2026-11-06 · source: `docs/storagemate-proposal-plan-v2.md` §API sử dụng

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
| POST | `/webhooks/zalo` | Zalo | Verify secret, enqueue into `inbound_messages`, 200 |
| GET | `/health` | Compose, CI | DB, queue, `getMe` |
| POST | `/api/auth/login` | Dashboard | Password → JWT |
| GET | `/api/period` | Dashboard | Shared period filter (calendar month + day range, plan §0): `month=YYYY-MM`, `from`, `to` → `{today,month,months[{value,label,hasData}],from,to,minDate,maxDate}`. Months from 2026-08 to current; `from`/`to` any days inside the month, `from`<=`to`, not after today; violations → 422 `{code:"invalid_period",message}` |
| GET | `/api/stock` | Dashboard | Stock page table, main warehouse: opening/inbound/outbound per destination/waste/variance/other/closing; `month,from,to,category,q,status,onlyMoved,sort,order,page,pageSize` |
| GET | `/api/stock/kpis/total-items` · `/kpis/in-stock` · `/kpis/variance` | Dashboard | Stock page cards → `{count}`; accept `month,from,to,category,q` (not `status`) |
| GET | `/api/transactions` | Dashboard | Inbound/Outbound list (main warehouse, cancelled pairs excluded), newest first: `type=IN\|OUT` (required), `month,from,to,q,page,pageSize` (default 50, max 200). IN → `{period,total,page,pageSize,items[{id,itemId,code,name,unit,qty,eventDate}]}`. OUT also takes `destinationId` (repeatable) + `unknownDestination`, items add `destinationId,destinationName,destinationKind` (null = unknown destination). `qty` is in the row's own `unit` |
| GET | `/api/transactions/out/destinations` | Dashboard | Outbound dropdown: places with OUT rows in the period → `{period,destinations[{id,name,kind,count}],unknown:{count}\|null}` (branches first, then partners by name) |
| GET | `/api/transactions/out/total` | Dashboard | Outbound box (A): `month,from,to,destinationId[],unknownDestination` → `{count}`. No destination params = all places incl. unknown; `unknownDestination=false` alone = empty selection → 0 |
| GET | `/api/transactions/out/by-destination` | Dashboard | Outbound table (B): same params + `limit` (1-100) → `{period,destinations[{id,name,kind,count,itemCount,lastDate}],unknown:{count,itemCount,lastDate}\|null}`, `count` desc |
| GET | `/api/transactions/out/daily` | Dashboard | Outbound stacked chart (C): same params → `{period,series[{key,name,kind}],days[{date,total,counts{key:n}}]}`; series = top 5 places + `other` + `unknown`; every day in the period, empty day = `counts:{}` |
| GET | `/api/transactions/out/top-items` | Dashboard | Outbound block (D): same params + `limit` (1-20, default 10) → `{period,items[{itemId,code,name,unit,count,qtyBase}]}` ranked by `count` (number of OUT rows), NOT by quantity (units differ); `qtyBase` in the item's base unit |
| GET | `/api/transactions/in/daily` | Dashboard | Inbound page chart: `month,from,to` → `{period,days[{date,count}]}`, every day in the period, empty day = 0 |
| GET | `/api/stock/destinations` | Dashboard | Stock page dynamic "Xuất" columns: destinations with OUT rows in the period (branches, partners, then unknown) |
| GET | `/api/items/categories` | Dashboard | Category dropdown `[{name,count}]`; optional repeatable `locationId` + `noTransactions` (same location filter as `/api/items`, so counts match the table) |
| GET | `/api/items/locations` | Dashboard | Catalog page location dropdown → `{locations[{id,name,kind,itemCount}],noTransactionsCount}`; warehouse then branches (no partners); `itemCount` = items with ledger rows at that location |
| GET | `/api/items` | Dashboard | Catalog table (read-only phase; archived items hidden): `locationId` (repeatable), `noTransactions`, `category` (repeatable), `q` (name / code / alias), `page`, `pageSize` (default 50, max 200) → `{total,page,pageSize,items[{id,code,name,category,unit,minQty,units[{name,factor}],matchedAlias}]}`, sorted by name. No location params = every item; `locationId` = union of locations; `noTransactions=true` adds items with no ledger row anywhere (`false` is ignored). `units` = packaging conversions without the base-unit row; `matchedAlias` set only when `q` matches an alias but not name/code |
| GET | `/api/transactions` | Dashboard | Ledger history, filter item/staff/date |
| POST | `/api/transactions/{id}/reverse` | Dashboard | Reversing row |
| GET/POST/PATCH | `/api/items` | Dashboard | Catalog, aliases, units, `min_stock` |
| GET/POST/PATCH | `/api/staff` | Dashboard | Staff, role, lock/unlock |
| POST | `/api/staff/{id}/invite` | Dashboard | Invite code + bot deeplink/QR |
| GET · PATCH | `/api/labels` · `/api/labels/{id}` | Dashboard | Label review (flywheel) |
| GET | `/api/reports/daily` · `/api/reports/monthly` | Dashboard | Period reports |
| POST · GET | `/api/chat/messages` | Web chat | Send into pipeline · poll replies |

| GET | `/api/locations` | Dashboard | Branch picker (branches only; no pick = main warehouse) |
| GET | `/api/dashboard/kpis/below-min` | Dashboard | Count of items with stock < `min_qty` (current state) |
| GET | `/api/dashboard/low-stock` | Dashboard | Items with lowest stock / `min_qty`, + avg daily OUT (30 d); `limit` ≤ 20 |
| GET | `/api/dashboard/tracked-items` | Dashboard | Item dropdown for the stock chart; `tracked` filter = `items.pinned` |
| GET | `/api/dashboard/stock/{item_id}/history` | Dashboard | End-of-day stock per day (running sum of `delta_base`); `days` ≤ 90 |
| GET | `/api/dashboard/kpis/stock-in` · `/kpis/items-in` · `/kpis/stock-out` · `/kpis/destinations` | Dashboard | Overview KPI cards, main warehouse: `month,from,to` → `{value,deltaPct}`. IN rows / distinct items IN / OUT rows / distinct destinations with OUT (unknown destination not counted). Cancelled pairs excluded. `deltaPct` vs the SAME day numbers of the previous month (clipped to its length); `null` when the previous value is 0 |
| GET | `/api/dashboard/kpis/in-stock` | Dashboard | Overview merged stock card: `month,from,to` → `{opening,closing,total}` = items with stock > 0 at start / end of the period, over items with a ledger row; `closing`/`total` equal the Stock page cards |
| GET | `/api/dashboard/in-out` | Dashboard | Overview bar chart: `month,from,to` → `{period,days[{date,inCount,outCount}]}`, every day in the period, empty day = 0 |
| GET | `/api/dashboard/staff` | Dashboard | Overview staff table, main warehouse (staff whose `default_location_id` is the warehouse): `month,from,to` → `{staff[{id,name,role,messages,syntaxOkPct,undoCount}]}`; `syntaxOkPct` null = no command messages in the period; `messages` sorted desc. Replaces the old `range`/`location_id` version |
| GET | `/api/dashboard/kpis/regex-rate` · `/kpis/retype` | Dashboard | Bot KPIs over `weeks`: regex % (+ `deltaPt`), failed-message % and count |
| GET | `/api/dashboard/parser-quality` | Dashboard | Weekly % regex / NER / LLM / failed (sums to 100), `weeks` |
| GET | `/api/dashboard/recent-transactions` | Dashboard | Overview: latest `limit` (1-50, default 10) IN/OUT rows of the main warehouse, mixed, independent of the period → `{items[{id,kind:"in"\|"out",name,unit,qty,eventDate,destinationName}]}` (`destinationName` only for `out` with a known destination; cancelled pairs and balancing rows excluded) |



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
| Valid secret, readable event | **200** `{"message":"Success"}` after `INSERT … ON CONFLICT (channel, external_id) DO NOTHING`; the worker answers |
| Same `message_id` again | **200**, still one row (dedup) |
| DB error on INSERT | **500** — Zalo does not retry, so the message is lost (logged) |
| Valid secret, unreadable event (e.g. `webhook.test`) | **200** `{"message":"Success"}`, warning logged, nothing sent |

Every accepted payload is appended raw to `data/zalo_samples/YYYY-MM-DD.jsonl` (gitignored; kept for field discovery).

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
