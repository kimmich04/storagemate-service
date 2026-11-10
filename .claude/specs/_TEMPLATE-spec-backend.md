# Storagemate — Spec: <tên tính năng / Phase N> (FastAPI)

> **Mục tiêu:** <1–3 câu: làm gì, cho ai, xong thì đạt được gì. Ghi rõ phần nào dùng stub/fake và điều kiện để bỏ.>
> Nguồn phạm vi: `docs/storagemate-proposal-plan-v2.md` § <tên mục>. Proposal và code lệch nhau → hỏi, không tự chọn.
>
> **Trạng thái:** 🔲 chưa làm · Owner: <tên> · Tạo: YYYY-MM-DD · Cập nhật: YYYY-MM-DD · Phase: <0–6>
> **Trạng thái code:** nháp | đã chạy `ruff check .` + `ruff format --check .` + `pytest` pass (ghi ngày)
>
> **Cách dùng file:** mỗi mục `### \`đường/dẫn\`` ở mục 9 là một file: tạo đúng đường dẫn đó và dán nguyên khối code.
>
> **Trước khi viết:** tra context7 (resolve library id → fetch docs) cho **mọi** thư viện dùng trong spec
> (FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, httpx, APScheduler 3.x, LangChain…), đúng version trong `pyproject.toml`;
> với Zalo Bot API đọc docs chính thức + `system-design/integrations.md`. Ghi lại ở mục 13. Không viết API từ trí nhớ.
> Đọc trước: `system-design/conventions.md`, `.claude/rules/python-fastapi.md`.

---

## 1. Phạm vi

| Có trong bản này | Chưa làm (để spec sau) |
|---|---|
| <endpoint / job / bảng / hành vi cụ thể> | <thứ cố ý bỏ ra + phase sẽ làm> |

---

## 2. Cài đặt & chạy

```bash
pip install -e ".[dev]"          # hoặc: uv pip install -e ".[dev]"
alembic upgrade head
fastapi dev                      # API: http://localhost:8000/docs
python -m app.worker             # worker (đúng 1 tiến trình)
pytest
```

Dependency mới (nếu có) — thêm vào `pyproject.toml`, ghi version tối thiểu và lý do:

| Gói | Version | Lý do |
|---|---|---|

Biến môi trường mới (khai báo trong `app/config.py` + `.env.example`; **không** đọc/commit `.env`):

| Biến | Bắt buộc | Mặc định | Ý nghĩa |
|---|---|---|---|

---

## 3. Cấu trúc thư mục

Chỉ vẽ phần spec tạo/sửa; đánh dấu `(mới)` / `(sửa)`. Theo layout domain hiện có (`system-design/directory-map.md`):

```
app/
├── main.py / api.py         # include router mới (sửa)
├── config.py                # biến môi trường mới (sửa)
└── <domain>/
    ├── router.py            # route sync `def` (DB sync), chỉ validate + gọi service
    ├── schemas.py           # Pydantic v2
    ├── models.py            # SQLAlchemy 2.0
    ├── service.py           # logic nghiệp vụ, không biết HTTP
    └── exceptions.py        # kế thừa app.exceptions.AppError (nếu cần)
alembic/versions/<rev>_<x>.py
tests/test_<x>.py
```

---

## 4. Data model & migration

| Bảng | Cột | Kiểu | Ràng buộc / index | Ghi chú |
|---|---|---|---|---|

- Ràng buộc đặt ở DB (`NOT NULL`, `UNIQUE`, `CHECK`, FK). Số lượng dùng `Numeric`, thời điểm `timestamptz`.
- `inventory_log` chỉ **INSERT**: sửa sai = thêm dòng đảo (`REVERSE`), không `UPDATE`/`DELETE`.
- Bảng mới mà Q&A cần đọc → cấp `SELECT` cho role read-only trong migration.
- Migration: `alembic revision --autogenerate -m "<x>"` → **đọc lại** file sinh ra → có cả `upgrade()` và `downgrade()`.
- Cập nhật `system-design/database-design.md`.

---

## 5. Hợp đồng API

| Method | Path | Auth | Request | Response | Mã lỗi |
|---|---|---|---|---|---|
| `GET` | `/api/<x>` | Bearer admin | query: … | `200` `<X>Read[]` | `401`, `422` |

- Mọi endpoint khai báo `response_model` (hoặc kiểu trả về) và `status_code`.
- Lỗi nghiệp vụ: raise lớp con của `AppError` → JSON `{"code", "message"}`; `422` giữ mặc định FastAPI.
- Danh sách có phân trang (`limit` ≤ <N>); không có endpoint trả về không giới hạn.
- Ngày `YYYY-MM-DD`, thời điểm ISO 8601 có múi giờ `+07:00`.
- Endpoint dashboard cần (khớp `src/api/types.ts` bên repo web): <liệt kê>. Cập nhật `system-design/api-contracts.md`.

---

## 6. Tích hợp Zalo Bot / hệ thống ngoài *(bỏ mục này nếu không đụng)*

| Hệ thống | Hướng | Endpoint / phương thức | Xác thực | Timeout / retry |
|---|---|---|---|---|
| Zalo Bot | vào | `POST /webhooks/zalo` | header `X-Bot-Api-Secret-Token`, so bằng `hmac.compare_digest` | — |
| Zalo Bot | ra | `https://bot-api.zaloplatforms.com/bot<TOKEN>/<method>` | token trong URL | `httpx` timeout tường minh, retry lỗi tạm thời |

- Webhook: sai secret → `403`, không lưu gì. Đúng → lưu raw payload + enqueue, trả `200` ngay; **không** parse/gọi LLM trong request.
- Dedup theo `message_id` (bỏ bản Zalo gửi lặp).
- Token nằm trong URL → **không** log URL gọi Zalo, không log `ZALO_BOT_TOKEN`; log lỗi httpx phải che URL.
- Tin trả lời bot bằng **tiếng Việt**; nội dung soạn ở `app/messaging/replies.py`.
- Payload mẫu thật: `tests/fixtures/<x>.json`; field chưa xác minh ghi vào `system-design/integrations.md`.
- Trong test: dùng fake (`tests/fakes.py`), **không** gọi Zalo/Gemini thật.

---

## 7. Luồng xử lý & quy tắc nghiệp vụ

```
Zalo → webhook (verify + lưu + enqueue, 200)
     → worker (1 tiến trình) → dispatcher → parser (regex → NER → LLM)
     → validate → [regex: ghi ledger | NER/LLM: chờ người gửi trả "OK"] → trả lời Zalo
```

- Quy tắc / công thức: <viết dạng kiểm được bằng test>.
- Tầng parse nào được ghi thẳng: **chỉ regex**; NER/LLM tạo pending, cần `OK` từ đúng người gửi.
- Transaction: <thao tác nào phải nằm chung một transaction>.
- Trường hợp biên: <tin trùng, đơn vị lạ, số âm, nguyên liệu chưa có trong catalog, tin ảnh, người lạ chưa có mã mời>.
- Job nền / lịch: <APScheduler trong worker, tần suất, chạy lại an toàn không>.
- Cập nhật `system-design/data-flow.md`.

---

## 8. Bảo mật & vận hành

- Auth / phân quyền: <admin JWT / manager / staff — ai gọi được gì>.
- Q&A / SQL agent chạy trên **DB role read-only**, không bao giờ trên role ghi.
- Validate mọi input ở biên bằng Pydantic; SQL chỉ qua ORM hoặc tham số hóa.
- Log không chứa secret, token, số điện thoại; lỗi trả cho client không lộ stack trace.
- Worker bắt lỗi ở vòng lặp, log, đánh dấu `inbound_messages.status = failed` kèm `error`.

---

## 9. Code từng file

### `app/<domain>/<file>.py`

```python
# code đầy đủ của file
```

---

## 10. Test

| Loại | File | Kiểm tra gì |
|---|---|---|
| Unit | `tests/test_<x>.py` | service / công thức / parser |
| API | `tests/test_<x>_api.py` | `TestClient` + `dependency_overrides` |
| Golden set | `ml/data/...` | parser đo trên tin thật của người (không dùng dữ liệu tổng hợp) |

- Test đặt tên theo hành vi: `test_returns_403_when_secret_header_missing`.
- Bug fix: viết test tái hiện trước, rồi sửa cho pass.
- Coverage mục tiêu ≥ 80% cho code mới.

---

## 11. Checklist nghiệm thu

**Chức năng:**
- [ ] <hành vi kiểm được, ví dụ: gửi "Nhập 50 kg bột mì" → có 1 dòng `inventory_log` IN 50 kg, bot trả lời tiếng Việt>

**Non-negotiables Storagemate:**
- [ ] `inventory_log` chỉ INSERT; sửa sai bằng dòng đảo
- [ ] Webhook trả 200 nhanh, chỉ lưu + enqueue; sai secret → 403
- [ ] Không log Zalo token / URL chứa token
- [ ] Q&A chạy trên role read-only
- [ ] Chỉ parse bằng regex mới ghi thẳng; NER/LLM cần `OK` của người gửi
- [ ] Vẫn chỉ đúng 1 worker
- [ ] Không đọc `.env` trong code/test/script
- [ ] Mọi tin bot gửi là tiếng Việt

**Chất lượng:**
- [ ] `ruff check .` và `ruff format --check .` sạch
- [ ] `pytest` pass, coverage code mới ≥ 80%
- [ ] `alembic upgrade head` rồi `alembic downgrade -1` chạy được trên DB trống
- [ ] `/docs` (OpenAPI) hiện đúng schema request/response

**Gate "done":**
- [ ] Cập nhật các file `system-design/` ở mục 12 + bump `last-updated` trong `system-design/README.md`
- [ ] Đổi dòng của spec này trong `STATUS.md` sang ✅

---

## 12. System-design docs sẽ đổi

- `system-design/<file>.md` — <phần nào>

---

## 13. Nguồn tham khảo

| Thư viện / hệ thống | Version | context7 id hoặc link docs | Đã dùng cho mục |
|---|---|---|---|
