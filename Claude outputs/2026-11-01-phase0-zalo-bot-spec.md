# Spec: Phase 0 — Zalo Bot setup (polling → webhook, no DB)
> Status: 🟡 in progress · Owner: Nash · Created: 2026-11-01 · Design approved: 2026-11-03

## Context / problem
Roadmap Phase 0 (overview.md). Prove the Zalo Bot channel end-to-end **before a database exists**:
receive a message (polling locally, webhook via ngrok), understand it, reply. Answer Phase-0 open
questions with real payloads.

Real staff data (118 messages from Kho tổng, Oct–Nov 2026) shows the plan-v2 single-line syntax
(`Nhập 50 kg bột mì 14h 28/10`) is **not** how staff write. They send a multi-line *phiếu*:
a header line (date + nhập/xuất + from → to) followed by many item lines. Requirement: **do not
change staff habits** — the parser adapts to them.

## Goals
- `getMe` succeeds; bot replies via `scripts/zalo_poll.py` (getUpdates) on the real Zalo bot.
- `POST /webhooks/zalo` verifies `X-Bot-Api-Secret-Token` (403 on mismatch), returns 200 immediately,
  processes in the background, replies via `sendMessage`.
- Parser reads the real *phiếu* format: 118/118 headers and 328/328 item lines of the fixture.
- Text "quick reply" menu (Zalo Bot API has no buttons).
- Duplicate item lines → bot asks A/B/C before accepting.
- Raw payloads saved to `data/zalo_samples/*.jsonl`; open questions answered in integrations.md.

- Static item catalog (123 items) + aliases + unit conversion → every line shows the catalog item and
  the quantity in the base unit (ĐVT gốc).

## Non-goals (this spec)
- Database, Alembic migrations, inventory ledger, stock lookup, invite codes, OK/Sai/Hủy.
- Editing the catalog at runtime (dashboard) — the catalog is a static file until the DB phase.
- Storing photos; OCR. NER / LLM fallback.
- Proactive-send script (`zalo_send.py`) — not needed now.

## Design summary

### Sources (official docs, read 2026-11-03)
bot.zaloplatforms.com/docs: create-bot, authorize, call-api, apis/{getMe, getUpdates, setWebhook,
testWebhook, deleteWebhook, getWebhookInfo, sendMessage, sendChatAction, sendPhoto}, webhook, error-code.

Facts from the docs that this design relies on:
- Webhook body is `{event_name, message}` (**no** `{ok, result}` wrapper); `getUpdates` returns
  `{ok, result: {event_name, message}}`. Adapter accepts both.
- `message.date` is Unix **milliseconds**. Image events carry `photo_url` + `caption`. `message_type`
  ∈ CHAT_TEXT / CHAT_PHOTO / CHAT_STICKER / CHAT_VOICE. Special-category users arrive as
  `message.unsupported.received`.
- `setWebhook` auto-verifies and returns `result.verification.outcome` (`webhook.ok` …). Zalo does not
  follow redirects; User-Agent is `Java/<version>`. `testWebhook` has a daily quota (426 when exceeded).
- Polling and webhook are mutually exclusive; `deleteWebhook` before polling.
- `sendMessage`: `text` 1–2000 chars, optional `parse_mode` = markdown | html. No buttons / reply markup.
- Token never expires until reset; it is part of the URL → must never be logged.
- Docs do **not** say whether Zalo retries a failed webhook → manual test below.

### Approach
FastAPI `BackgroundTasks`: webhook verifies, dedups, saves sample, `add_task(process, msg)`, returns 200.
When the DB arrives, that one line becomes `queue.enqueue(msg)` and `process()` moves into the worker
unchanged. Polling script calls the same `process()`, so local tests exercise the production path.

### Files
| File | Role | When DB arrives |
|---|---|---|
| `app/config.py` (edit) | + `ZALO_API_BASE`, `ZALO_SAMPLES_DIR` | keep |
| `app/main.py` (edit) | `lifespan` creates one shared `ZaloClient` on `app.state` | keep |
| `app/channels/base.py` | `InboundMessage`, `Reply(text, quick_replies)` dataclasses | keep |
| `app/channels/zalo_client.py` | `ZaloClient` (httpx.AsyncClient): get_me, get_updates, set_webhook, delete_webhook, get_webhook_info, test_webhook, send_message, send_chat_action; `ZaloApiError`; retry 408/429/403 (max 3, backoff + jitter); token redacted | keep |
| `app/channels/zalo.py` | `parse_update(payload) -> InboundMessage \| None`; `render(reply) -> list[str]` (numbered menu, split ≤ 2000 chars); `save_sample(payload)` | keep |
| `app/channels/router.py` | `POST /webhooks/zalo` | `add_task` → `enqueue` |
| `app/messaging/queue.py` | `SeenCache` (message_id, TTL 1 h) + `async process(msg, client)` | → Postgres queue + worker |
| `app/messaging/pending.py` | `PendingStore` (chat_id → pending phiếu + question, TTL 10 min) | → `pending_actions` table |
| `app/messaging/dispatcher.py` | `handle(msg) -> list[Reply]` — pure, no FastAPI, no I/O | called by worker |
| `app/messaging/replies.py` | All Vietnamese reply texts + menu + templates | keep |
| `app/parser/regex.py` | `parse_phieu(text, received_at) -> Phieu \| ParseError` | + validate vs catalog |
| `app/parser/catalog.json` | 123 items: base unit, conversions, bundles (generated) | seed `items` + `units` |
| `app/parser/aliases.py` | Alias rules + verified exact aliases | → `items.aliases` column |
| `app/parser/catalog.py` | `match(name)`, `to_base(item, qty, unit)` | query DB instead of JSON |
| `scripts/build_catalog.py` | Reviewed xlsx → `catalog.json` | keep (seed script) |
| `scripts/zalo_poll.py` | getWebhookInfo guard → loop getUpdates → parse → save → process | keep |
| `scripts/zalo_set_webhook.py` | subcommands `set` · `info` · `test` · `delete` | keep |
| `.gitignore` (edit) | + `data/`, `tests/fixtures/*.txt` (real shop data) | keep |

### Flow
```
Webhook:  Zalo POST /webhooks/zalo
          ├─ secret mismatch            → 403
          ├─ parse_update() is None     → save_sample, log warning, 200
          └─ ok → save_sample → add_task(process, msg, client) → 200 {"message":"Success"}
Polling:  zalo_poll.main() → get_webhook_info (url set → exit) → loop get_updates(30)
          → parse_update → save_sample → await process(msg, client)

process(msg, client):
  seen.add_if_new(message_id) else return
  send_chat_action(chat_id, "typing")
  replies = dispatcher.handle(msg)
  for r in replies: for chunk in zalo.render(r): send_message(chat_id, chunk, parse_mode="markdown")
  except Exception → logger.exception + best-effort "⚠️ Bot gặp lỗi, bạn gửi lại giúp mình nhé"
```

### dispatcher.handle(msg) — order
1. Pending question for this chat_id and text ∈ {A, B, C} (case/diacritics-insensitive) → answer it.
   Any other text clears the pending question, then continue.
2. Event sticker / voice / unsupported → `reply_text_only()`.
3. Event image: caption present → treat caption as text (+ "📷 Đã nhận ảnh"); no caption →
   `reply_photo_only()`.
4. Normalized text (lower, no diacritics, trimmed): `menu` | `?` → menu; `1` → template Xuất;
   `2` → template Nhập; `3` | `huong dan` → help.
5. First line looks like a phiếu header (contains xuat | nhap | hang ve | gui hang) → `parse_phieu`
   → summary reply; if duplicate lines → summary + A/B/C question, store pending.
6. Otherwise → `reply_unknown()` (includes menu).

### Menu (text quick reply)
```
📋 Chọn nhanh (gõ số):
1 · Mẫu Xuất
2 · Mẫu Nhập
3 · Hướng dẫn
```
`1`/`2` send two messages: a lead line, then the template alone (easy long-press copy), dated today:
`ngày 03/11 xuất từ kho tổng sang kho 220` / `Tên hàng: số lượng` (and `ngày 03/11 nhập hàng về kho tổng`).
`Reply.quick_replies` holds the options; the Zalo adapter renders them as a numbered list (web chat can
render real buttons later).

### Parser — `parse_phieu`
Output: `Phieu{action: IN|OUT, date, date_note, from_loc, to_loc, items: [ItemLine{qty, unit, name, note}],
warnings, duplicate_groups}`.

Header (first line, normalized):
- Date `(ngày)? d{1,2}/d{1,2}`. Correction `thật ra là d/m` overrides it (+ warning). No year → current
  year; if result is > tomorrow → previous year. No date → `received_at` + note "tự lấy giờ nhận tin".
- Action: `xuất` | `gửi hàng` → OUT; `nhập` | `hàng về` → IN.
- Route: `từ X sang|cho|ra|đi Y`, `X -> Y`, `(X -> Y)`, `về X`, `(nội bộ)`. Location aliases:
  `khi tổng` → kho tổng, `220` → kho 220, `pq` → Phú Quốc. Unknown names kept as typed. Missing → `?`.
- Inline phiếu (no item lines): item = text between the action word and `(`; route from the parentheses.

Item lines, tried in order:
1. `name : qty [unit] [(note)]` — `Viên nén caramel: 24`, `thìa nhựa vàng : 6 gói`
2. `name qty unit` — `Unity trứng 15 hộp`, `đĩa tròn 20cm 4 cái`
3. `qty [pure-unit] name` — `48 hộp cafe trứng hoà tan`, `2 dĩa tròn 18cm`

Pure units (may lead a line): bịch, hộp, thùng, gói, thanh, cái, pack, tệp, chai, lon, kg.
Trailing units also allow set, bộ, túi. Words like túi / set / bộ / ly / cốc at the start stay part of
the name (`30 túi mer nhỏ` → name "túi mer nhỏ"). **"viên nén" is a product name (Eggpresso), never
the unit "viên".** Numbers inside names (`18cm`, `12oz`, `3 vị`, `599k`) are kept in the name.
Unparsable line → reported individually with the hint `Tên hàng: số lượng`.

### Catalog, aliases, units (static, no DB)
Source: Excel `THEO DÕI XUẤT NHẬP TỒN KHO TỔNG SG T10.2026` (master sheet + "Quy cách đóng gói").
Reviewed table: `storagemate-don-vi-va-ten-goi.xlsx` (sheets "Quy đổi đơn vị", "Tên gọi khác").

- `scripts/build_catalog.py` reads the reviewed xlsx → `app/parser/catalog.json`
  `{code, name, base_unit, conversions: {unit: factor}, bundle}`. DB phase: seeds `items` + `units`.
- `app/parser/aliases.py`: global rewrite rules (VN / viên nén → Eggpresso, cf / cafe → cà phê,
  EY / egg yolk → eggyolk, khăn giấy → giấy ăn vuông, áo thun → áo phông, hoà tan → sấy thăng hoa …)
  + exact aliases verified against the Excel (túi mer nhỏ → Túi giấy logo nhỏ, cốc/ly wall lớn →
  Ly double wall 160ml, ống hút nhỏ → Ống hút size 6, cf trứng EY / sấy / hoà tan → Hộp cà phê trứng sấy …).
- `app/parser/catalog.py`: `match(name) -> CatalogItem | Ambiguous | None` — exact alias first, then
  token overlap on normalized names (prototype: 247/328 lines high-confidence before exact aliases).
- Line output: `ItemLine{raw, qty, unit, item, qty_base, base_unit, status: ok | unknown | ambiguous}`.
  No unit typed → base unit. Unit typed and in `conversions` → `qty_base = qty × factor`.
  Unit typed but not convertible for that item → keep as typed + ⚠️.

Conversion rules (Nash, 2026-11-03: **every Hộp / Thanh item = 24 per thùng**, overrides the sheet's
40 and 50; verified: "2 thùng cf trứng" = 48 on 17/10, 19/10, 26/10):

| Item group | Base unit | Conversions |
|---|---|---|
| Hộp cà phê trứng / kem béo / sữa sấy; Unity (dừa, sữa đá, trứng, 3 vị) | Hộp | thùng = 24 |
| Eggpresso (11 flavours) | Thanh | thùng = 24 · viên = 0,1 |
| Set cafe hoà tan 3 vị | Pack | thùng = 100 |
| Cốc giấy 8oz · nắp 8oz · nắp 12oz · cốc nhựa 12/16oz | Cái | thùng = 1000 |
| Cốc giấy 12oz | Cái | thùng = 500 |
| Nắp cốc nhựa | Cái | thùng = 2000 (cao) or 1000 (thấp) → bot asks |
| Thìa nhựa vàng | Cái | túi = gói = 50 (verified: 6 gói = 300) |
| Giấy ăn vuông eggyolk | Kg | bịch = 1 (verified) |
| Đường que logo | Gói | túi = 100 |
| Túi giấy logo nhỏ | Cái | tệp = 10 |
| Ống hút size 6 / 8 / 12 | Cái | thùng = 3000 / 2000 / 1000 · túi = bịch = 250 (6, 8) |

Alias decisions (Nash, 2026-11-03):
- Size not in the catalog → map to the nearest **larger** size of the same item, with ⚠️ in the reply
  (`dĩa tròn 22cm` → Đĩa tròn trứng lòng vàng 20cm, the largest).
- `bột kem trứng` → Bột kem trứng (200g), unit Túi (not the Gói item).
- `15 thùng unity` is a real 15 thùng = 360 hộp; the Excel (15 on 26/10) is the error. A Unity line
  without a flavour is `ambiguous` → bot asks which flavour. Reconciliation test lists this row as a
  known Excel error, not a parser failure.

Bundles (from "Quy cách") — **exploded into components** (Nash, 2026-11-03), verified against Excel:
- `bộ trứng màu X` / `set trứng X` → 1 Bát trứng ngâm X + 1 Cốc trứng có nắp X + 1 Zig café X
  (no wooden tray). Excel 1/10, 18/10, 31/10: "2 bộ trứng màu vàng" = 2 of each.
- Cup bundles (Ly Espresso, Cốc Capu, Cốc 3 màu xanh, Hoàng hôn, Bình minh: 1 bộ = 1 cốc + 1 đĩa)
  explode **only when the line says "bộ"**. A bare cup line counts cups only (Excel 19/10: "cốc 3 màu
  xanh: 2" → no saucer); saucers sent alone appear as their own line (2/10 "đĩa kê be: 2").
  Note `(không có đĩa)` always means cup only.
- Reply shows the bundle line, then its components indented:
  `1. Bộ trứng vàng — 2 bộ` / `   → Bát trứng ngâm vàng 2 · Cốc trứng có nắp vàng 2 · Zig café vàng 2`.

### Reply example
```
📦 XUẤT · kho tổng → kho 220
📅 31/10/2026  ⚠️ sửa từ 13/10 theo ghi chú "thật ra là"
1. Eggpresso caramel vani — 24 thanh
2. Eggpresso Arabica Specialty — 24 thanh
🧪 Bản thử: chưa ghi sổ
```
```
📦 XUẤT · kho tổng → kho 220
📅 17/10/2026
1. Hộp cà phê trứng sấy thăng hoa — 2 thùng (= 48 hộp)
2. dĩa tròn 22cm — 2  ❓ chưa có trong danh mục
```
Duplicate lines (same normalized name + qty + unit): one group at a time —
`❓ Dòng 1 và 2 giống nhau. A · Cùng loại → tổng 4 bịch · B · Hai mẫu khác nhau → gõ lại phiếu, ghi rõ
tên từng mẫu · C · Ghi trùng → chỉ tính 2 bịch`. A merges, C drops the duplicate, both resend the
summary; B asks to resend; no answer in 10 min → dropped.

### Error handling
| Case | Handling |
|---|---|
| Wrong secret | 403, nothing saved, body not logged |
| Unknown event / missing fields | save sample, warn, 200, no reply |
| Zalo 408 / 429 / 403 | retry ≤ 3, exponential backoff + jitter |
| Zalo 400 / 404 | no retry, log error |
| Zalo 401 | no retry, log "token sai hoặc đã reset" |
| Exception in `process()` | `logger.exception`, best-effort error reply, no traceback to user |
| Reply > 2000 chars | split on line boundaries |
| Polling while webhook set | `zalo_poll.py` exits with "chạy `zalo_set_webhook.py delete` trước" |

Secrets: `httpx`/`httpcore` loggers at WARNING; never log request URLs; `ZaloApiError` messages
redact the token as `***`.

## Tasks
- [ ] `config.py`, `channels/base.py`, `channels/zalo_client.py`
- [ ] `channels/zalo.py` (parse_update, render, save_sample)
- [ ] `parser/regex.py` + `tests/test_regex.py` on the 118-message fixture
- [ ] `scripts/build_catalog.py` → `parser/catalog.json`; `parser/aliases.py`, `parser/catalog.py`
      + `tests/test_catalog.py` (conversions, aliases, reconciliation vs Excel)
- [ ] `messaging/replies.py`, `messaging/pending.py`, `messaging/dispatcher.py` + `tests/test_dispatcher.py`
- [ ] `messaging/queue.py` (SeenCache, process)
- [ ] `channels/router.py`, `main.py` lifespan + `tests/test_webhook.py`, `tests/test_zalo_adapter.py`
- [ ] `scripts/zalo_poll.py`, `scripts/zalo_set_webhook.py`; `.gitignore`
- [ ] Manual test: polling, then webhook via ngrok (checklist below)
- [ ] Update affected system-design docs + bump last-updated
- [ ] Update this spec's row in STATUS.md to ✅

## Test / acceptance criteria
Automated (`pytest`, no real Zalo calls, `ZaloClient` stubbed):
- All 118 fixture headers → date + action; all 328 item lines parsed; tricky cases asserted
  (`18cm`, `12oz: 1000`, `thật ra là`, `khi tổng`, inline phiếu, `30 túi mer nhỏ`).
- Catalog: every conversion row in the table above; "viên nén" never read as unit; 6 gói thìa = 300 cái.
- **Reconciliation (golden set):** parse the 118 messages, sum `qty_base` per (date, item, destination)
  and compare with the Excel sheets TỔNG NHẬP / XUẤT KHO 220 / XUẤT CHO ĐỐI TÁC-NỘI BỘ / XUẤT CHO PHÚ
  QUỐC. Report match rate + every mismatch (known Excel error: 26/10 Unity — Excel 15, real 360 hộp).
- Adapter: wrapped and unwrapped payloads, image with caption, unsupported event.
- Dispatcher: menu 1/2/3, duplicate question A/B/C, pending expiry.
- Webhook: wrong secret → 403; valid → 200 and `process` scheduled; duplicate message_id ignored.

Manual on the real bot (after resetting the leaked token):
1. Polling: `zalo_set_webhook.py info` → no URL → `zalo_poll.py` → send `menu`, `1`, fixture messages
   #2 (duplicate), #6 (date correction), #11 (14 lines), #45 / #53 (inline), a photo with caption, a sticker.
2. Inspect `data/zalo_samples/*.jsonl` (field names, `date` unit, caption).
3. Webhook: `fastapi dev` + `ngrok http --url=<domain> 8000` → `zalo_set_webhook.py set` →
   `verification.outcome == webhook.ok` → repeat step 1 messages → `curl` with wrong secret → 403.
4. Retry test: stop the server, message the bot, restart, check whether the message appears in samples.

## Open — decide before the DB phase
- Data model: real data is **transfers between locations** (kho tổng → kho 220 / Dinh / đối tác /
  nội bộ / Phú Quốc), not IN/OUT of one store as in plan v2.
- Catalog maintenance after go-live: new sizes / names staff invent (handled today by the rules below).
- Catalog moves to DB tables + dashboard editing.
- Photo evidence storage; OK/Sai confirmation and Hủy.
- Answer from the retry test → whether the queue needs extra safeguards.

## System-design docs this will change
- `integrations.md` — Zalo Bot facts above (payload shape, ms dates, photo fields, no buttons, verification).
- `data-flow.md` — BackgroundTasks path for the no-DB phase; polling path.
- `api-contracts.md` — `POST /webhooks/zalo` contract.
