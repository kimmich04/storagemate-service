# Glossary
> last-updated: 2026-11-02

Ubiquitous language. Code identifiers in English, bot replies in Vietnamese.

| Term (VN) | Code / meaning | Notes |
|-----------|----------------|-------|
| Nhập | `action = IN` — stock received | Command `Nhập [qty] [unit] [item] [giờ] [ngày]` |
| Xuất | `action = OUT` — stock used/removed | Must not make stock negative |
| Tồn / tồn kho | `current_stock` view, Σ IN − Σ OUT in `qty_base` | `Tồn [item]` command |
| Sổ cái | `inventory_log` — append-only ledger, source of truth | Never UPDATE/DELETE |
| Bản ghi bù trừ | Reversing row: `reverses_id` + flipped action | How `Hủy` and dashboard fixes work |
| Hủy | Reverse own latest row, ≤ 30 min | `REVERSE_WINDOW` |
| Bản chờ | `pending_actions` — NER/LLM parse awaiting `OK`/`Sai` | Expires 10 min |
| OK / Sai | Confirm / reject a pending action | Typed text, no buttons |
| Mã mời | `invite_codes` — 6-char, 1-use, 24 h | Links Zalo account to `staff` |
| Nhân viên / staff | `role = staff` | Stock commands only |
| Quản lý / manager | `role = manager` | + Q&A + `Báo cáo` + reports |
| Admin | Dashboard user (shop owner), `admins` table | Only JWT user |
| Nguyên liệu | `items` | Has `aliases` (no-diacritic, abbreviations), `min_stock` |
| Đơn vị / quy đổi | `units.factor` to `items.base_unit` | 1 thùng = 24 hộp → factor 24 |
| Channel adapter | `app/channels/*` → `InboundMessage` | Zalo, web; Zalo OA later = new adapter |
| Parser cascade | regex → NER (ONNX) → LLM | Stops at first success |
| `parser_source` | `regex` / `ner` / `llm` | Only `regex` writes without confirmation |
| Golden set | 100–200 real labelled messages | Never mixed with synthetic/train data |
| Flywheel | Confirmed samples → retrain NER → HF Hub | Batch, human-in-the-loop |
| `event_time` vs `received_at` | Time written in the message vs webhook arrival | Both `timestamptz` |
| Pha | Roadmap phase 0–6 | See overview.md |
