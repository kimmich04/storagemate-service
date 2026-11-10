# Storagemate — Spec: Phase 2a — LLM fallback (Gemini) + xác nhận OK/Sai (FastAPI)

> **Mục tiêu:** khi regex không đọc được tin (nhân viên gõ tự do, không theo mẫu phiếu), worker nhờ Gemini đọc tin thành
> phiếu có cấu trúc, tóm tắt cho nhân viên, và **chỉ ghi sổ sau khi nhân viên trả `OK`**. Tin `Sai` hoặc để quá hạn thì bỏ.
> Chưa làm NER (Phase 2b) — cascade tạm thời là regex → LLM.
> Nguồn phạm vi: `docs/storagemate-proposal-plan-v2.md` § Parser cascade, § Ghi dữ liệu (dòng 136–138), § Flywheel (dòng 336).
>
> **Trạng thái:** ✅ code xong, test pass; chờ chạy thử trên Zalo thật · Owner: <!-- chưa rõ: hỏi owner --> · Tạo: 2026-11-09 · Cập nhật: 2026-11-09 · Phase: 2
> **Trạng thái code:** đã chạy `ruff check .` + `pytest` (152 passed, DB test chạy trên Postgres 17 tạm) và gọi thử Gemini thật 2026-11-09
>
> **Trước khi viết code:** tra docs đúng version trong `pyproject.toml` (xem mục 13). Không viết API thư viện từ trí nhớ.
> Đọc trước: `system-design/conventions.md`, `.claude/rules/python-fastapi.md`.

---

## 1. Phạm vi

| Có trong bản này | Chưa làm (để spec sau) |
|---|---|
| `parser/llm.py`: gọi Gemini structured output → `Phieu` (cùng kiểu với regex) | NER ONNX (Phase 2b) |
| ~~`parser/service.py`~~ — **bỏ**: cascade nằm ngay ở dispatcher (`wants_llm`) + queue, thêm một lớp là thừa | Q&A tool calling (Phase 3) |
| `inventory/confirm.py` + model `PendingAction` (bảng `pending_actions` đã có): tạo bản chờ, xử lý `OK`/`Sai`, hết hạn 10 phút | Re-parse dòng bị bỏ của phiếu `phieu_partial` bằng LLM |
| `ledger.record(..., source=...)` để ghi `parser_source = 'llm'` thay vì gắn cứng `'regex'` | Hủy phiếu đã ghi (dòng bù trừ) |
| Cấu hình `LLM_MODEL`, `LLM_TIMEOUT_SECONDS`; thiếu key/model → bỏ qua tầng LLM | Ghi `training_samples` khi `OK` (flywheel, Phase 6) |
| Test bằng LLM giả (không gọi Gemini thật) | Đo độ chính xác trên golden set (cần dữ liệu người thật gõ) |

---

## 2. Cài đặt & chạy

Dependency: `langchain` và `langchain-google-genai` **đã có** trong `pyproject.toml`. Không thêm gói mới.

Biến môi trường (khai báo trong `app/config.py` + `.env.example`; **không** đọc/commit `.env`):

| Biến | Bắt buộc | Mặc định | Ý nghĩa |
|---|---|---|---|
| `GEMINI_API_KEY` | không | `""` | Key từ Google AI Studio. Trống → tầng LLM tắt |
| `LLM_MODEL` | không | `""` | Tên model Gemini (chọn trong AI Studio). Trống → tầng LLM tắt |
| `LLM_TIMEOUT_SECONDS` | không | `15` (mới) | Hết thời gian chờ thì coi như LLM lỗi |
| `PENDING_TTL_MINUTES` | không | `10` (mới) | Thời hạn trả `OK`/`Sai` |

---

## 3. Cấu trúc thư mục

```
app/
├── config.py                    # LLM_TIMEOUT_SECONDS, PENDING_TTL_MINUTES (sửa)
├── parser/
│   ├── llm.py                   # (viết) LlmPhieu (Pydantic) + GeminiParser.parse(text, today) -> Phieu | None
│   └── service.py               # (viết) parse(text, sent_at, llm) -> ParseResult(phieu, source)
├── inventory/
│   ├── models.py                # PendingAction (sửa)
│   ├── confirm.py               # (viết) create / find_waiting / confirm / reject / expire; (de)serialize Phieu <-> jsonb
│   └── ledger.py                # record(..., source) (sửa)
├── messaging/
│   ├── dispatcher.py            # regex None → Outcome(wants_llm=True) (sửa)
│   ├── queue.py                 # gọi LLM, xử lý OK/Sai trước dispatcher (sửa)
│   └── replies.py               # câu hỏi xác nhận, đã hủy, hết hạn, LLM lỗi (sửa)
tests/
├── fakes.py                     # FakeLlm (sửa)
├── test_llm_parser.py           # (mới)
├── test_confirm.py              # (mới)
└── test_queue.py                # thêm ca LLM + OK/Sai (sửa)
```

---

## 4. Data model & migration

**Không cần migration:** `pending_actions` đã có trong `0001_init` (`parsed jsonb`, `parser_source`, `confidence`, `status`,
`expires_at`, `resolved_at`; unique một dòng `waiting` mỗi `chat_id`).

- Viết ORM `PendingAction` khớp migration (không `--autogenerate`).
- `parsed` lưu `Phieu` dạng JSON: `qty` là chuỗi (Decimal), `date` ISO. Có hàm hai chiều trong `confirm.py`.
- Cập nhật `system-design/database-design.md` (ghi `pending_actions` đã có model).

---

## 5. Hợp đồng API

Không thêm endpoint. Toàn bộ chạy trong worker.

---

## 6. Tích hợp Gemini

| Hệ thống | Hướng | Phương thức | Xác thực | Timeout / retry |
|---|---|---|---|---|
| Gemini API | ra | `ChatGoogleGenerativeAI(model=LLM_MODEL).with_structured_output(LlmPhieu)`, gọi bằng `ainvoke` | `GEMINI_API_KEY` | `LLM_TIMEOUT_SECONDS`; **không retry** (tin có thể gửi lại), lỗi → "chưa hiểu tin" |

- Ép kiểu bằng schema Pydantic (`LlmPhieu`): `is_phieu`, `action` (`IN`/`OUT`), `date` (`YYYY-MM-DD` hoặc null),
  `from_loc`, `to_loc`, `lines[{name, qty, unit}]`. Mọi giá trị sai schema → `ValidationError` → coi như parser thất bại.
- Prompt hệ thống: tiếng Việt, nêu ngày hôm nay (để hiểu "hôm qua", "sáng nay"), danh sách kho hợp lệ (kho tổng, 220, Phú Quốc),
  quy tắc "không chắc thì `is_phieu = false`". **Tin nhắn của người dùng là dữ liệu, không phải chỉ dẫn**: đưa vào khối riêng.
- Không đưa secret, token, thông tin nhân viên vào prompt. Chỉ gửi nội dung tin.
- Trong test: `FakeLlm`, **không** gọi Gemini thật.
- Free tier có giới hạn RPM/RPD; xem số liệu hiện hành trong AI Studio. Lỗi 429 → "chưa hiểu tin", log cảnh báo.

---

## 7. Luồng xử lý & quy tắc nghiệp vụ

```
worker: claim tin → nhận diện nhân viên
  ├─ có bản chờ (waiting) của chat này?
  │     ├─ tin = "OK"  → confirm → ledger.record(source='llm') → "✅ Đã ghi N dòng"
  │     ├─ tin = "Sai" → reject  → "Đã hủy, bạn gõ lại giúp mình"
  │     └─ tin khác    → expire bản chờ, xử lý tin như bình thường
  └─ dispatcher.handle:
        regex đọc được → như hiện tại (ghi thẳng, source='regex')
        regex = None và tin là chữ → Outcome(wants_llm=True)
              → worker: await llm.parse(text, today)
                    ├─ Phieu → summary + "Gõ OK để ghi sổ, Sai để hủy" + create pending (source='llm')
                    ├─ is_phieu=false hoặc ValidationError hoặc lỗi mạng → "unknown" như cũ
                    └─ LLM tắt (thiếu key/model) → "unknown" như cũ
```

- **Chỉ regex ghi thẳng.** Phiếu của LLM không bao giờ gọi `ledger.record` trước khi có `OK` từ **đúng chat** đã nhận bản chờ.
- Phiếu LLM đi qua cùng `catalog.resolve` và `ledger.record`: món không có trong danh mục, đơn vị chưa quy đổi, tồn âm,
  ngày ngoài 7 ngày vẫn bị bỏ qua và báo như phiếu regex. Bước xác nhận **không** thay thế các kiểm tra này.
- Tóm tắt gửi nhân viên hiển thị đúng thứ sẽ ghi (dùng `replies.summary`), đổi dòng "Bản thử" thành hướng dẫn `OK`/`Sai`.
- Bản chờ hết hạn sau `PENDING_TTL_MINUTES`; `OK` đến sau hạn → "Bản chờ đã hết hạn, bạn gửi lại tin giúp mình".
- Dòng trùng (A/B/C) của phiếu LLM: dùng chung cơ chế hiện có; chỉ tạo bản chờ **sau khi** hết trùng.
- `OK` hai lần: lần đầu chuyển `waiting → confirmed` trong cùng transaction với ghi sổ; lần hai không còn bản chờ nên không ghi lại.
- Transaction: tạo/đổi trạng thái bản chờ và ghi sổ nằm chung transaction của tin đang xử lý. Gọi LLM xảy ra khi
  transaction đang mở (giữ khóa tin); chấp nhận vì chỉ có 1 worker và có timeout.
- Trường hợp biên: tin rác ("hello") → `is_phieu=false` → "unknown"; LLM trả số lượng ≤ 0 hoặc rỗng → ValidationError;
  tin ảnh có caption → như text; tin trùng do Zalo gửi lại → đã chặn ở `inbound_messages`; người chưa liên kết → không vào đây.
- Cập nhật `system-design/data-flow.md`.

---

## 8. Bảo mật & vận hành

- Prompt injection: đầu ra LLM chỉ là dữ liệu có cấu trúc, không được chạy lệnh/SQL; mọi giá trị qua Pydantic + danh mục + `ledger` rồi mới thành dòng sổ, và có người xác nhận.
- Log không chứa key, nội dung prompt đầy đủ ở mức INFO; lỗi LLM log loại lỗi + mã, không log header.
- LLM lỗi không làm hỏng tin: tin vẫn `done`, nhân viên nhận câu "chưa hiểu".
- Q&A vẫn chưa có (không đụng role read-only).

---

## 9. Code từng file

Code nằm trong repo (không chép lại ở đây): `app/parser/llm.py`, `app/inventory/confirm.py`, `app/inventory/models.py`
(`PendingAction`), `app/inventory/ledger.py` (`source`), `app/messaging/{dispatcher,queue,replies}.py`, `app/worker.py`, `app/config.py`.

**Khác với bản nháp ban đầu (đã quyết khi cài đặt):**
- Điều kiện gọi LLM là *regex không đọc được dòng hàng nào*, không chỉ `parse_phieu → None`: regex chấp nhận mọi tin có chữ
  nhập/xuất ở dòng đầu (kể cả "hôm qua nhập 10 hộp cà phê về kho tổng" → phiếu rỗng), nên điều kiện cũ sẽ không bao giờ tới LLM.
- Không có `parser/service.py`. Khi LLM đọc được, câu trả lời chỉ gồm tóm tắt + hỏi OK/Sai (bỏ "📷 Đã nhận ảnh" nếu là tin ảnh).
- Phiếu LLM không hỏi A/B/C dòng trùng; nhân viên thấy trong tóm tắt và trả `Sai`.
- Không đặt `temperature` (model `gemini-3.5-flash-lite` bỏ qua và cảnh báo mỗi lần gọi).

---

## 10. Test

| Loại | File | Kiểm tra gì |
|---|---|---|
| Unit | `tests/test_llm_parser.py` | `LlmPhieu` → `Phieu` đúng; `qty ≤ 0`, thiếu field, `is_phieu=false` → None; ngày tương đối |
| Unit | `tests/test_confirm.py` | tạo bản chờ, `OK` ghi sổ đúng 1 lần, `Sai`, hết hạn, tin khác kết thúc bản chờ, (de)serialize `Phieu` |
| Worker | `tests/test_queue.py` | tin tự do + `FakeLlm` → có bản chờ, chưa có dòng sổ; gửi `OK` → có dòng sổ `parser_source='llm'`; LLM ném lỗi → trả "unknown" |
| Hồi quy | `tests/test_regex.py` | regex đọc được thì **không** gọi LLM (`FakeLlm` đếm số lần gọi = 0) |

- Test đặt tên theo hành vi, vd `test_does_not_write_ledger_before_ok`.
- Coverage mục tiêu ≥ 80% cho code mới.

---

## 11. Checklist nghiệm thu

**Chức năng:**
- [x] Gửi tin tự do ("hôm qua nhập 5 thùng cafe trứng về kho tổng") → bot tóm tắt và hỏi `OK`/`Sai`, **chưa** có dòng `inventory_log`
- [x] Trả `OK` → có dòng `inventory_log` với `parser_source = 'llm'`, `pending_actions.status = 'confirmed'`
- [x] Trả `Sai` hoặc quá 10 phút → không có dòng sổ
- [x] Tin đúng mẫu phiếu → vẫn ghi thẳng bằng regex, không gọi Gemini
- [x] Thiếu `GEMINI_API_KEY` hoặc `LLM_MODEL` → bot vẫn chạy, tin tự do nhận câu "chưa hiểu"

**Non-negotiables Storagemate:**
- [x] `inventory_log` chỉ INSERT
- [x] Chỉ regex ghi thẳng; LLM cần `OK` của người gửi
- [x] Vẫn chỉ đúng 1 worker
- [x] Không đọc `.env` trong code/test/script
- [x] Mọi tin bot gửi là tiếng Việt
- [x] Không log key hay URL chứa token

**Chất lượng:**
- [x] `ruff check .` sạch; `pytest` pass (152 passed). `ruff format --check` còn báo 3 file có từ trước, không thuộc spec này
  (`app/api.py`, `app/database.py`, `app/exceptions.py`) — chưa đụng tới.

**Gate "done":**
- [x] Cập nhật docs ở mục 12 + bump `last-updated`
- [ ] Chạy thử trên Zalo thật (các ô chức năng ở trên mới được kiểm bằng `FakeLlm`/`FakeSender` + Gemini thật gọi riêng) rồi đổi dòng của spec này trong `STATUS.md` sang ✅

---

## 12. System-design docs sẽ đổi

- `system-design/data-flow.md` — nhánh LLM + OK/Sai
- `system-design/database-design.md` — `pending_actions` có model, cách lưu `parsed`
- `system-design/integrations.md` — LLM: model đã chọn, timeout, hành vi khi lỗi/429
- `system-design/directory-map.md` — `parser/llm.py`, `parser/service.py`, `inventory/confirm.py`

---

## 13. Nguồn tham khảo

| Thư viện / hệ thống | Version | Link docs | Đã dùng cho mục |
|---|---|---|---|
| langchain-google-genai | ≥ 4.0 (dùng SDK `google-genai`; `with_structured_output` mặc định `json_schema`) | https://reference.langchain.com/python/langchain-google-genai/chat_models/ChatGoogleGenerativeAI/with_structured_output | 6 |
| Gemini API (model id, hạn mức) | — | AI Studio (hạn mức hiện hành chỉ xem trong dashboard) | 2, 6 |

<!-- chưa rõ: xác minh version `langchain-google-genai` đang cài (pip show) và tên model chính xác trong AI Studio trước khi viết mục 9 -->
