# Phase 0 — Zalo Bot (no DB) Implementation Plan

> Spec: `.claude/specs/2026-11-01-phase0-zalo-bot-spec.md`. Workflow: Claude builds each task in a scratch
> copy of `storagemate-service`, runs the tests, then hands the files over task by task; Nash reviews,
> copies into the repo, runs the same command, commits. Steps use `- [ ]` for tracking.

**Goal:** A Zalo bot that reads real multi-line *phiếu* messages, resolves items/units against a static
catalog, and replies with a summary — via polling locally and via webhook in production. No database.

**Architecture:** Webhook verifies the secret, returns 200 and runs `process()` in FastAPI
`BackgroundTasks`; polling calls the same `process()`. `process()` → `dispatcher.handle()` (pure) →
`parser` (regex + catalog) → `replies` → `ZaloClient.send_message`. RAM stores (`SeenCache`,
`PendingStore`) stand in for the future Postgres tables.

**Tech stack:** Python 3.11+, FastAPI, httpx, pydantic-settings, openpyxl (scripts/tests only), pytest, ruff.
No new runtime dependency (`openpyxl` is already in the `ml` extra; add it to `dev`).

---

## File map

| File | New/Edit | Responsibility |
|---|---|---|
| `app/config.py` | edit | + `ZALO_API_BASE`, `ZALO_SAMPLES_DIR` |
| `app/channels/base.py` | new | `InboundMessage`, `Reply` |
| `app/parser/normalize.py` | new | `fold()` (lower, no diacritics, single spaces) — shared |
| `app/parser/regex.py` | new | `parse_phieu()` → `Phieu` with `RawLine`s |
| `app/parser/aliases.py` | new | rewrite rules + verified exact aliases |
| `app/parser/catalog.py` | new | load `catalog.json`; `resolve(RawLine) -> ResolvedLine` (match, convert, explode) |
| `app/parser/catalog.json` | generated | 123 items, base unit, conversions, bundles |
| `scripts/build_catalog.py` | new | reviewed xlsx → `catalog.json` |
| `app/messaging/replies.py` | new | all Vietnamese texts, menu, templates, summary formatting |
| `app/messaging/pending.py` | new | `PendingStore` (TTL 10 min) |
| `app/messaging/dispatcher.py` | new | `handle(msg, now, pending) -> list[Reply]` |
| `app/channels/zalo_client.py` | new | `ZaloClient`, `ZaloApiError`, retry, redaction |
| `app/channels/zalo.py` | new | `parse_update`, `render`, `save_sample` |
| `app/messaging/queue.py` | new | `SeenCache`, `process()` |
| `app/channels/router.py` | edit | `POST /webhooks/zalo` |
| `app/main.py` | edit | `lifespan` → `app.state.zalo` |
| `scripts/zalo_poll.py`, `scripts/zalo_set_webhook.py` | new | dev polling; set/info/test/delete |
| `.gitignore`, `pyproject.toml` | edit | ignore `data/`, `tests/fixtures/*.txt|*.xlsx`; `openpyxl` in `dev` |
| `tests/fixtures/` | Nash copies | `tin_nhan_118.txt`, `ton_kho_t10.xlsx` (gitignored) |

Shared types (fixed names, used across tasks):
```python
InboundMessage(channel: str, message_id: str, chat_id: str, sender_id: str, display_name: str,
               event: Literal["text","image","sticker","voice","unsupported","other"],
               text: str | None, photo_url: str | None, sent_at: datetime)
Reply(text: str, quick_replies: list[str] = [], parse_mode: str | None = "markdown")
RawLine(raw: str, name: str, qty: Decimal, unit: str | None, note: str | None)
Phieu(action: Literal["IN","OUT"], date: date, date_note: str | None, from_loc: str, to_loc: str,
      lines: list[RawLine], bad_lines: list[str], warnings: list[str])
ResolvedLine(line: RawLine, item: CatalogItem | None, status: Literal["ok","unknown","ambiguous"],
             qty_base: Decimal | None, base_unit: str | None, components: list[tuple[str, Decimal]],
             warning: str | None)
```

---

### Task 1: Config + shared dataclasses
**Files:** edit `app/config.py`; new `app/channels/base.py`, `app/parser/normalize.py`; test `tests/test_normalize.py`
- [ ] Test: `fold("Xuất  Từ KHO Tổng") == "xuat tu kho tong"`; `fold("Đĩa")=="dia"`.
- [ ] Implement; add `ZALO_API_BASE="https://bot-api.zaloplatforms.com"`, `ZALO_SAMPLES_DIR="data/zalo_samples"`.
- [ ] Run `pytest tests/test_normalize.py -v` → 2 passed. Commit `feat(channels): shared message types`.

### Task 2: Phiếu parser (regex, no catalog)
**Files:** new `app/parser/regex.py`; test `tests/test_regex.py` (+ fixture `tests/fixtures/tin_nhan_118.txt`)
- [ ] Tests (fixture split on `^\d+\.\s`; skipped if fixture missing):
  - all 118 → `Phieu` not None; 95 `OUT` / 23 `IN`; total `len(lines)` = 328; `bad_lines` empty.
  - `"13/10 xuất từ kho tổng sang kho 220 ( thật ra là 31/10\n\tViên nén caramel: 24"` → date 31/10, `date_note` set.
  - `"21/10 xuất từ khi tổng sang kho 220\n\tcốc nhựa 12oz: 1000"` → `from_loc=="kho tổng"`, line name `"cốc nhựa 12oz"`, qty 1000.
  - `"ngày 19/10 xuất bột drip: 30 (kho tổng -> 220)"` → 1 line, `to_loc=="kho 220"`.
  - `"2 dĩa tròn 18cm"` → qty 2, name `"dĩa tròn 18cm"`; `"30 túi mer nhỏ"` → unit None, name `"túi mer nhỏ"`;
    `"Unity trứng 15 hộp"` → unit `"hộp"`; `"5 viên nén houseblend"` → unit None (viên nén = name).
  - No date → `date == received_at.date()` and `date_note == "tự lấy ngày nhận tin"`; `"5/11"` on 2026-11-03 → 2025-11-05.
  - `"hello"` → None.
- [ ] Run → fail; implement; run → all pass. Commit `feat(parser): multi-line phiếu regex`.

### Task 3: Catalog, aliases, units, bundles
**Files:** new `scripts/build_catalog.py`, `app/parser/aliases.py`, `app/parser/catalog.py`, generated `app/parser/catalog.json`; test `tests/test_catalog.py`
- [ ] Run `python scripts/build_catalog.py data/catalog/storagemate-don-vi-va-ten-goi.xlsx` → writes 123 items.
- [ ] Tests (each resolves a `RawLine`):
  - `2 thùng cafe trứng hoà tan` → Hộp cà phê trứng sấy thăng hoa, `qty_base==48`, `base_unit=="Hộp"`.
  - `Viên nén caramel: 24` → Eggpresso caramel vani, 24 Thanh. `1 thùng VN robusta` → 24 Thanh.
  - `thìa nhựa vàng : 6 gói` → 300 Cái. `2 bịch khăn giấy egg yolk` → Giấy ăn vuông eggyolk 2 Kg.
  - `Ống hút nhỏ: 1 thùng` → Ống hút size 6, 3000. `Nắp cốc nhựa: 1 thùng` → status ambiguous (cao/thấp).
  - `Túi mer nhỏ: 30` → Túi giấy logo nhỏ; `Cốc wall lớn: 3` → Ly café double wall 160ml.
  - `2 dĩa tròn 22cm` → Đĩa tròn … 20cm + warning "không có size 22cm". `bột kem trứng: 5` → Bột kem trứng (200g) Túi.
  - `15 thùng unity` → ambiguous (flavour), `qty_base==360`.
  - `2 bộ trứng màu vàng` → components Bát trứng ngâm vàng 2, Cốc trứng có nắp vàng 2, Zig café vàng 2.
  - `cốc 3 màu xanh: 2 ( không có đĩa)` → Cốc sứ 3 màu xanh 2, no components.
  - Over the fixture: ≥ 95 % of 328 lines `ok`, none crash.
- [ ] Run → fail; implement; pass. Commit `feat(parser): static catalog + unit conversion`.

### Task 4: Reconciliation vs Excel (golden set)
**Files:** test `tests/test_reconcile.py` (+ fixture `tests/fixtures/ton_kho_t10.xlsx`)
- [ ] Test: parse + resolve all October messages, sum `qty_base` (and components) per (day, item, sheet by
  destination: TỔNG NHẬP / XUẤT KHO 220 / ĐỐI TÁC-NỘI BỘ / PHÚ QUỐC); compare with sheet cells.
  Assert match rate ≥ 90 % of non-empty cells; print every mismatch; `KNOWN_EXCEL_ERRORS = {(26, "Unity cà phê Trứng", "XUẤT KHO 220")}` excluded.
- [ ] Run `pytest tests/test_reconcile.py -v -s` → pass, mismatch report printed. Fix aliases from the report, re-run. Commit `test(parser): reconcile October with Excel`.

### Task 5: Replies, pending store, dispatcher
**Files:** new `app/messaging/replies.py`, `app/messaging/pending.py`, `app/messaging/dispatcher.py`; test `tests/test_dispatcher.py`
- [ ] Tests (`handle(msg, now, pending)`):
  - `menu` / `?` → 1 Reply with `quick_replies == ["Mẫu Xuất","Mẫu Nhập","Hướng dẫn"]`.
  - `1` → 2 Replies; second text starts `ngày 03/11 xuất từ kho tổng sang kho 220`. `2` → nhập template. `3` → help.
  - fixture #11 → 1 Reply containing 14 numbered lines and `🧪 Bản thử`.
  - fixture #74 (duplicate) → Reply contains `❓ Dòng 2 và 3`; then `a` → summary shows
    `Giấy ăn vuông eggyolk — 4 bịch (= 4 Kg)`; `c` → keeps one line (2 Kg); `b` → asks to resend;
    after 11 min `a` → treated as normal text (unknown).
  - sticker event → text-only hint; image without caption → photo hint; image with caption = phiếu → summary + `📷`.
  - `hello` → unknown + menu.
- [ ] Run → fail; implement; pass. Commit `feat(messaging): dispatcher, menu, duplicate question`.

### Task 6: Zalo HTTP client
**Files:** new `app/channels/zalo_client.py`; test `tests/test_zalo_client.py` (httpx `MockTransport`)
- [ ] Tests: `send_message` posts JSON `{chat_id,text,parse_mode}` to `/bot<TOKEN>/sendMessage`;
  429 twice then 200 → 3 calls, success; 401 → `ZaloApiError` after 1 call; `str(error)` never contains the token;
  `get_updates` returns `None` on 408.
- [ ] Run → fail; implement (async, one `httpx.AsyncClient`, backoff 0.5·2ⁿ + jitter, max 3, `httpx` logger WARNING); pass.
  Commit `feat(channels): Zalo Bot API client`.

### Task 7: Zalo adapter
**Files:** new `app/channels/zalo.py`; test `tests/test_zalo_adapter.py`
- [ ] Tests: webhook body (no wrapper) and getUpdates body (`{ok,result}`) → same `InboundMessage`;
  `date` ms → aware datetime Asia/Ho_Chi_Minh; image → `event=="image"`, `text==caption`, `photo_url` set;
  unsupported → `event=="unsupported"`; garbage → None; `render(Reply(quick_replies=[...]))` appends numbered menu;
  a 2 500-char reply → 2 chunks split on newlines, each ≤ 2000; `save_sample` appends one JSON line to `<dir>/YYYY-MM-DD.jsonl`.
- [ ] Run → fail; implement; pass. Commit `feat(channels): Zalo adapter`.

### Task 8: process() + SeenCache
**Files:** new `app/messaging/queue.py`; test `tests/test_queue.py` (fake sender)
- [ ] Tests: `process(msg, sender)` → `send_chat_action` then `send_message` × n; same `message_id` twice → sent once;
  dispatcher raising → one error reply `⚠️ Bot gặp lỗi`, exception logged, no raise.
- [ ] Run → fail; implement; pass. Commit `feat(messaging): process pipeline`.

### Task 9: Webhook route + lifespan
**Files:** edit `app/channels/router.py`, `app/main.py`; test `tests/test_webhook.py` (override `app.state.zalo` with fake)
- [ ] Tests: missing/wrong `X-Bot-Api-Secret-Token` → 403; valid text payload → 200 `{"message":"Success"}` and fake
  sender received the reply; unknown event → 200, nothing sent; `/health` still 200.
- [ ] Run → fail; implement; pass; `pytest` (all) green; `ruff check . && ruff format --check .` clean.
  Commit `feat(webhook): POST /webhooks/zalo with background processing`.

### Task 10: Scripts + repo hygiene
**Files:** new `scripts/zalo_poll.py`, `scripts/zalo_set_webhook.py`; edit `.gitignore`, `pyproject.toml`
- [ ] `python scripts/zalo_set_webhook.py --help` lists `set info test delete`.
- [ ] `zalo_poll.py` with a webhook set → prints "chạy `zalo_set_webhook.py delete` trước", exit 1.
- [ ] Commit `chore(scripts): polling + webhook management`.

### Task 11: Manual test — polling (Nash, ~10 min)
- [ ] Reset bot token in Zalo Bot Creator; fill `.env` (`ZALO_BOT_TOKEN`, `ZALO_WEBHOOK_SECRET` = `python -c "import secrets;print(secrets.token_urlsafe(32))"`).
- [ ] `python scripts/zalo_set_webhook.py info` → `url: ""`. `python scripts/zalo_poll.py`.
- [ ] In Zalo send: `menu`, `1`, fixture #2, #6, #11, #45, #53, a photo with caption, a sticker. Each reply matches Task 5.
- [ ] Open `data/zalo_samples/<today>.jsonl`: confirm `date` ms, `photo_url`, `caption` field names.

### Task 12: Manual test — webhook via ngrok (Nash, ~15 min)
- [ ] `fastapi dev` · `ngrok http --url=<domain>.ngrok-free.app 8000` · `python scripts/zalo_set_webhook.py set` → `outcome: webhook.ok`.
- [ ] Repeat Task 11 messages; log shows `200` before the reply.
- [ ] `curl -X POST https://<domain>/webhooks/zalo -H "X-Bot-Api-Secret-Token: wrong" -d '{}'` → 403.
- [ ] Retry test: stop server, message bot, start server; note whether the message appears in samples.

### Task 13: Docs + status
- [ ] Update `integrations.md` (payload facts, retry result), `data-flow.md`, `api-contracts.md`; bump last-updated.
- [ ] Spec row in `STATUS.md` → ✅. Commit `docs: phase 0 zalo bot`.
