# storagemate-service

Backend của **Storagemate**: AI agent ghi nhận nhập/xuất kho cho cửa hàng F&B từ tin nhắn Zalo, tính tồn kho real-time và trả lời câu hỏi của quản lý.

- **API** (FastAPI): webhook Zalo + REST API cho dashboard
- **Worker**: xử lý hàng đợi tin nhắn, parser (regex → NER → LLM), báo cáo định kỳ
- **PostgreSQL**: sổ cái nhập/xuất (append-only), hàng đợi, danh mục
- **ML**: train NER tiếng Việt (ViDeBERTa → ONNX), không deploy

## Đang làm tới đâu — đọc trước khi code

> Cập nhật 2026-11-07 · người làm: Nash · nhánh `develop`

**Trạng thái:** đang ở **Pha 1**. Bot Zalo ghi phiếu nhập/xuất vào PostgreSQL. Nhân viên phải nhập mã mời mới dùng được bot.
Bảng tiến độ: [`.claude/specs/STATUS.md`](.claude/specs/STATUS.md).

| Spec | Làm gì | Trạng thái |
|---|---|---|
| [Phase 0 — Zalo bot](.claude/specs/2026-11-01-phase0-zalo-bot-spec.md) | Nhận tin Zalo, regex đọc phiếu, hỏi lại khi tên món trùng | ✅ |
| [Phase 1 — DB + sổ kho](.claude/specs/2026-11-06-phase1-db-ledger-spec.md) | Hàng đợi tin trong Postgres, 1 worker, ghi `inventory_log` từng dòng, báo dòng chưa ghi | 🟡 polling đã test qua Zalo; còn test webhook |
| [Phase 1 — Mã mời](.claude/specs/2026-11-06-phase1-invite-code-spec.md) | Chat chưa liên kết gửi mã 6 ký tự → gắn với nhân viên | ✅ polling đã test qua Zalo |

**Đọc một spec theo thứ tự này** (mọi spec cùng khuôn [`_TEMPLATE-spec-backend.md`](.claude/specs/_TEMPLATE-spec-backend.md)):

1. **Đầu file — `Trạng thái`**: xong chưa, bao nhiêu test pass, ngày cập nhật.
2. **§0 Quyết định đã chốt**: bảng "Owner đã chốt" là quyết định của owner, không tự đổi. Bảng "Quyết định của Claude" là đề xuất, muốn đổi thì hỏi owner.
3. **§1 Phạm vi**: có gì trong bản này, cái gì để spec sau.
4. **§2 Cài đặt & chạy**: dựng PostgreSQL 16 + seed, chạy bot bằng polling, các ca test qua Zalo (T1–T6, I1–I6) kèm kết quả từng ca.
5. **§7 Luồng xử lý**: quy tắc nghiệp vụ (luật 7 ngày, chặn xuất vượt tồn, route của từng tin).
6. **§11 Checklist nghiệm thu**: ô đã tick là đã kiểm, ô trống là việc còn lại.

**Báo cáo kết quả lần làm 2026-11-06 → 07** nằm ngay trong spec:

| Muốn biết | Xem |
|---|---|
| Test tự động | Dòng `Trạng thái code` đầu spec. Lần chạy gần nhất: `ruff` sạch, `pytest` 133 pass trên DB `storagemate_test` |
| Test thật qua Zalo | Spec mã mời §2.1: bảng I1–I6, cột "Kết quả 2026-11-07". Spec DB-ledger §2.4: các ca T1–T6 |
| Lỗi đã gặp khi dựng DB + cách sửa | Spec DB-ledger §2.6 |
| Việc còn lại | §11 của từng spec (ô chưa tick) + cột Status trong `STATUS.md` |
| Kiến trúc đã đổi | [`.claude/system-design/data-flow.md`](.claude/system-design/data-flow.md) §2 (mã mời), §3a (đường đi của tin ở Pha 1) |

**Chạy thử nhanh Pha 1:** làm theo spec DB-ledger §2.2 → §2.3 (cần PostgreSQL 16 và file seed), rồi tạo mã bằng
`python scripts/dev_db.py --invite "Tên"` và gửi mã đó cho bot.

## Mục lục

1. [Yêu cầu](#1-yêu-cầu)
2. [Cài đặt từng bước](#2-cài-đặt-từng-bước)
3. [Chạy bằng Docker Compose](#3-chạy-bằng-docker-compose)
4. [Lệnh thường dùng](#4-lệnh-thường-dùng)
5. [Biến môi trường](#5-biến-môi-trường)
6. [Cấu trúc thư mục](#6-cấu-trúc-thư-mục)
7. [Kiến trúc source code](#7-kiến-trúc-source-code)
8. [Dashboard (UI) gọi API ở đâu](#8-dashboard-ui-gọi-api-ở-đâu)
9. [Train model NER](#9-train-model-ner)
10. [Xử lý lỗi thường gặp](#10-xử-lý-lỗi-thường-gặp)
11. [Quy trình đóng góp](#11-quy-trình-đóng-góp)

---

## 1. Yêu cầu

| Công cụ | Phiên bản | Bắt buộc? | Ghi chú |
|---|---|---|---|
| Git | bất kỳ | ✅ | Để clone repo |
| Python | **3.11 – 3.13** | ✅ | **Không dùng 3.14** (`pyproject.toml` chặn, thư viện ML chưa hỗ trợ). Khuyên dùng 3.13 |
| Docker Desktop (+ WSL 2 trên Windows) | bản mới | ⬜ | Chỉ cần khi chạy Postgres/worker bằng Docker Compose |
| GPU NVIDIA (≥ 8 GB VRAM) | — | ⬜ | Chỉ cần khi train NER trong `ml/` |

Kiểm tra nhanh:

```bash
git --version
python --version        # hoặc trên Windows: py -0p  (liệt kê mọi bản Python đã cài)
docker --version        # nếu dùng Docker
```

---

## 2. Cài đặt từng bước

### Bước 1 — Clone repo

```bash
git clone https://github.com/kimmich04/storagemate-service.git
cd storagemate-service
```

### Bước 2 — Tạo và kích hoạt virtual environment

**Windows (PowerShell):**

```powershell
py -3.13 -m venv .venv          # đổi 3.13 thành bản 3.11–3.13 bạn có (xem: py -0p)
.venv\Scripts\activate
python --version                # phải ra 3.11.x – 3.13.x
```

**macOS / Linux:**

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python --version
```

Đầu dòng lệnh hiện `(.venv)` là đã kích hoạt thành công.

### Bước 3 — Cài thư viện

```bash
pip install --upgrade pip
pip install -e ".[dev]"
```

- `-e` (editable): sửa code là có hiệu lực ngay, không cần cài lại.
- `[dev]`: thêm `pytest`, `ruff` để test và lint.

Thấy dòng `Successfully installed ... storagemate-service` là xong.

### Bước 4 — Tạo file `.env`

```powershell
copy .env.example .env          # Windows
```

```bash
cp .env.example .env            # macOS / Linux
```

Chạy thử chưa cần điền gì. Khi làm tới phần Zalo / Gemini / DB thì điền theo [mục 5](#5-biến-môi-trường).

### Bước 5 — Chạy server

```bash
fastapi dev
```

Mở trình duyệt:

| URL | Thấy gì |
|---|---|
| http://127.0.0.1:8000/docs | Swagger UI, thử API trực tiếp |
| http://127.0.0.1:8000/health | `{"status": "ok"}` |
| http://127.0.0.1:8000/api/openapi.json | OpenAPI spec (dashboard sinh client từ đây) |

### Bước 6 — Chạy test

```bash
pytest
```

Chưa đặt `TEST_DATABASE_URL` thì các test cần DB bị **skip**. Muốn chạy đủ, tạo DB riêng `storagemate_test` rồi đặt
`TEST_DATABASE_URL` trỏ vào đó (spec DB-ledger §2.5). Không trỏ vào DB dev, vì DB test bị xoá sạch mỗi lần chạy.

---

## 3. Chạy bằng Docker Compose

Chạy đủ **api + worker + postgres** (cần Docker Desktop đang mở):

```bash
docker compose up --build
```

| Service | Cổng | Ghi chú |
|---|---|---|
| `api` | 8000 | http://localhost:8000/docs |
| `worker` | — | Xem log: `docker compose logs -f worker` |
| `postgres` | 5432 | user / pass / db: `storagemate` |

Dừng: `Ctrl + C`, rồi `docker compose down`. Thêm `-v` nếu muốn **xóa luôn dữ liệu DB**.

---

## 4. Lệnh thường dùng

| Việc | Lệnh |
|---|---|
| Chạy API (dev, tự reload) | `fastapi dev` |
| Chạy worker | `python -m app.worker` |
| Test | `pytest` |
| Lint + tự sửa | `ruff check . --fix` |
| Format code | `ruff format .` |
| Tạo migration mới | `alembic revision --autogenerate -m "mo_ta_ngan"` |
| Áp migration | `alembic upgrade head` |
| Lùi 1 migration | `alembic downgrade -1` |

---

## 5. Biến môi trường

Khai báo trong `.env` (mẫu: `.env.example`), đọc bởi `app/config.py`. **Không commit `.env`.**

| Biến | Dùng cho | Ví dụ |
|---|---|---|
| `DATABASE_URL` | Kết nối Postgres | `postgresql+psycopg://storagemate:storagemate@localhost:5432/storagemate` |
| `DATABASE_URL_READONLY` | User chỉ đọc cho Q&A agent | `postgresql+psycopg://qa_reader:***@localhost:5432/storagemate` |
| `TEST_DATABASE_URL` | DB riêng cho pytest (bị xoá sạch mỗi lần chạy). Để trống thì test DB bị skip | `postgresql+psycopg://postgres:***@127.0.0.1:5432/storagemate_test` |
| `WORKER_POLL_SECONDS` | Hàng đợi rỗng thì worker ngủ bao lâu | `1.0` |
| `ZALO_BOT_TOKEN` | Gọi Zalo Bot API | lấy từ Zalo Bot Creator |
| `ZALO_WEBHOOK_SECRET` | Xác thực webhook | chuỗi ngẫu nhiên ≥ 32 ký tự |
| `PUBLIC_BASE_URL` | URL public cho webhook | `https://<ten>.ngrok-free.app` |
| `JWT_SECRET` | Ký token đăng nhập dashboard | chuỗi ngẫu nhiên |
| `GEMINI_API_KEY` | Q&A + parser fallback | lấy từ Google AI Studio |
| `LLM_MODEL` | Tên model Gemini | xem trong AI Studio |
| `HF_MODEL_REPO` | Nơi lưu model NER | `<user>/storagemate-ner` |
| `NER_MODEL_PATH` | File ONNX worker nạp | `models/ner/model_quantized.onnx` |
| `CORS_ORIGINS` | Domain dashboard được gọi API | `http://localhost:5173,https://<app>.vercel.app` |
| `TZ` | Múi giờ | `Asia/Ho_Chi_Minh` |

Tạo chuỗi ngẫu nhiên: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

---

## 6. Cấu trúc thư mục

Chia theo **domain** (FastAPI "Bigger Applications" + fastapi-best-practices): mỗi domain có `router` (endpoint) · `schemas` (Pydantic) · `models` (bảng DB) · `service` (logic).

```
storagemate-service/
├── app/
│   ├── main.py          # tạo app, CORS, mount router            🖥️
│   ├── api.py           # gom router cho UI, prefix /api          🖥️
│   ├── config.py        # Settings đọc .env
│   ├── database.py      # engine, session, get_db
│   ├── models.py        # Base SQLAlchemy
│   ├── exceptions.py    # lỗi chung
│   ├── worker.py        # process worker
│   ├── auth/  items/  staff/  inventory/  labels/  reports/  chat/   # 🖥️ domain có API cho UI
│   ├── channels/        # ⚡ webhook Zalo + adapter kênh
│   ├── messaging/       # ⚙️ hàng đợi, phân loại tin
│   ├── parser/          # ⚙️ regex → NER (ONNX) → LLM → validate
│   └── qa/              # ⚙️ Q&A agent (Gemini + LangChain)
├── tests/               # test, cấu trúc giống app/
├── alembic/             # migration DB
├── ml/                  # train NER (không deploy)
├── models/              # file .onnx (không commit)
├── scripts/             # seed dữ liệu, tạo admin, set webhook Zalo
├── Dockerfile · docker-compose.yml · pyproject.toml · .env.example
```

🖥️ UI gọi · ⚡ Zalo gọi · ⚙️ nội bộ

---

## 7. Kiến trúc source code

> Tài liệu gốc (chi tiết hơn, luôn được cập nhật cùng code): [`.claude/system-design/`](.claude/system-design/README.md) —
> `architecture.md`, `directory-map.md`, `data-flow.md`, `database-design.md`, `api-contracts.md`, ADR trong `decisions/`.
> Phạm vi nghiệp vụ: [`docs/storagemate-proposal-plan-v2.md`](docs/storagemate-proposal-plan-v2.md).

### 7.1 Trạng thái hiện thực

Repo đang ở **Pha 1** (xem [Đang làm tới đâu](#đang-làm-tới-đâu--đọc-trước-khi-code)). Đã chạy được:
webhook + `scripts/zalo_poll.py` enqueue, `app/worker.py` → `messaging/queue.py` → `messaging/dispatcher.py` →
`inventory/ledger.py`, mã mời (`staff/service.py`), migration `0001_init`, script dev `scripts/dev_db.py`.
Chưa làm: NER/LLM, `Hủy`, báo cáo, Q&A, API dashboard. Phần mô tả các module đó dưới đây là kiến trúc đích theo roadmap.

### 7.2 Hai process, một codebase

Cùng một Docker image chạy 2 process khác nhau, giao tiếp **chỉ qua Postgres** (không Redis/Celery — ADR 0003).

```mermaid
flowchart LR
  zalo[Zalo Bot API] -->|POST /webhooks/zalo| api
  dash[Dashboard SPA] -->|/api/* + JWT| api
  subgraph image[storagemate-service image]
    api[api — app/main.py<br/>FastAPI / Uvicorn]
    worker[worker — app/worker.py<br/>python -m app.worker]
  end
  api -->|INSERT ... ON CONFLICT DO NOTHING| db[(PostgreSQL 16)]
  worker -->|SELECT ... FOR UPDATE SKIP LOCKED| db
  worker -->|sendMessage / sendChatAction| zalo
  worker --> gemini[Gemini API]
  hf[Hugging Face Hub] -.->|model NER .onnx| worker
```

| Process | Entry point | Việc làm | Không được làm |
|---|---|---|---|
| **api** | `app/main.py` (`fastapi dev`) | Webhook Zalo: kiểm secret → chuẩn hóa → enqueue → trả 200 ngay. REST `/api/*` cho dashboard. Nhận tin web chat | Không parse, không gọi LLM, không gửi Zalo trong request webhook |
| **worker** | `app/worker.py` | Claim hàng đợi, nhận diện người gửi, phân loại, parser cascade, ghi sổ / tạo bản chờ, trả lời, chạy APScheduler báo cáo, Q&A | **Chỉ chạy đúng 1 instance** (APScheduler không được bắn 2 lần) |

### 7.3 Lớp core dùng chung (`app/`)

| File | Vai trò | Ai dùng |
|---|---|---|
| `main.py` | Tạo `FastAPI`, CORS (`CORS_ORIGINS`), `register_exception_handlers`, mount `api_router` ở `/api` và `channels.router` ở `/webhooks`, endpoint `/health`. `custom_generate_unique_id` đặt operationId `<tag>-<tên hàm>` | Uvicorn |
| `api.py` | **Nơi duy nhất** đăng ký router cho dashboard (`auth`, `items`, `staff`, `stock`, `transactions`, `labels`, `reports`, `chat`) | `main.py` |
| `config.py` | `Settings` (pydantic-settings) đọc `.env`; `settings` singleton | mọi module |
| `database.py` | SQLAlchemy 2.0 engine (sync, psycopg 3), `SessionLocal`, dependency `get_db` | router, service, worker |
| `models.py` | `Base` declarative cho mọi bảng | `*/models.py`, Alembic |
| `exceptions.py` | `AppError` + handler trả JSON thống nhất | service raise, `main.py` đăng ký |
| `worker.py` | Vòng lặp hàng đợi + khởi động APScheduler + nạp ONNX một lần | `python -m app.worker` |

### 7.4 Cấu trúc bên trong một domain

Mỗi domain (`auth`, `items`, `staff`, `inventory`, `labels`, `reports`, `chat`) theo cùng khuôn:

```
app/<domain>/
├── router.py    # HTTP: khai báo endpoint, Depends(get_db / get_current_user), gọi service — không chứa logic
├── schemas.py   # Pydantic v2: request/response (…Create, …Read, …Filter)
├── service.py   # Logic nghiệp vụ, nhận Session, trả model/schema; raise AppError
└── models.py    # Bảng SQLAlchemy của domain
```

Luồng gọi: `router → service → models (DB)`; `schemas` dùng ở cả router và service.

### 7.5 Chi tiết từng module

**🖥️ Domain có API cho dashboard**

| Module | File chính | Trách nhiệm |
|---|---|---|
| `auth/` | `router.py`, `security.py`, `dependencies.py`, `service.py`, `models.py` | Đăng nhập admin, ký/kiểm JWT (PyJWT), hash mật khẩu (pwdlib argon2). `get_current_user` gắn vào router cần đăng nhập. Bảng `admins` |
| `items/` | `service.py`, `models.py` | Danh mục nguyên liệu, alias, đơn vị + hệ số quy đổi (1 thùng = 24 hộp), `min_stock`. Hàm tìm theo tên/alias dùng chung cho `parser/validate.py`. Bảng `items`, `units` |
| `staff/` | `service.py`, `models.py` | CRUD nhân viên (role `staff`/`manager`), sinh mã mời 6 ký tự (1 lần, TTL 24h), khóa `chat_id` khi nhập sai > 5 lần/15 phút. Bảng `staff`, `invite_codes` |
| `inventory/` | `ledger.py`, `confirm.py`, `service.py`, `models.py`, `router.py` | **Sổ cái**. `ledger.py`: quy đổi về đơn vị cơ bản, chặn tồn âm, ghi `inventory_log`, tạo bản ghi bù trừ. `confirm.py`: tạo `pending_actions` cho tin do NER/LLM đọc, xử lý `OK`/`Sai`/`Hủy`. `service.py`: query tồn (`current_stock`) + lịch sử cho UI và `qa/tools.py`. Router tách `stock_router` và `transactions_router` |
| `labels/` | `service.py`, `models.py` | Lưu mẫu đã xác nhận vào `training_samples`, manager review mẫu bị `Sai`, export BIO cho `ml/scripts/train_ner.py` |
| `reports/` | `service.py`, `jobs.py` | `service.py`: tồn đầu + nhập − xuất = tồn cuối theo kỳ. `jobs.py`: lịch APScheduler (21:30 hằng ngày, 07:00 ngày 1 hằng tháng, `Asia/Ho_Chi_Minh`) — chạy trong worker |
| `chat/` | `service.py`, `router.py` | Web chat demo: `POST /api/chat/messages` đưa tin vào **cùng hàng đợi** với Zalo; UI poll `GET` để lấy trả lời |

**⚡ Kênh vào/ra**

| File | Trách nhiệm |
|---|---|
| `channels/router.py` | `POST /webhooks/zalo`: so `X-Bot-Api-Secret-Token` bằng `hmac.compare_digest` (sai → 403, không lưu), enqueue, trả 200 ngay |
| `channels/base.py` | `InboundMessage` (dataclass chung) + interface `ChannelAdapter` (`parse_inbound`, `send_text`) |
| `channels/zalo.py` | `ZaloAdapter`: payload Zalo Bot → `InboundMessage`; gửi trả lời qua `zalo_client` |
| `channels/web.py` | `WebAdapter`: tin web chat → `InboundMessage` |
| `channels/zalo_client.py` | HTTPX gọi Zalo Bot API (`sendMessage`, `sendChatAction`, `getMe`, `setWebhook`). Retry 408/429/403 (backoff + jitter, tối đa 3); 400/401/404 không retry. **Token nằm trong URL → không bao giờ log** |

`channels/` là code **duy nhất** biết hình dạng payload Zalo. Thêm kênh mới (vd Zalo OA) = thêm 1 adapter.

**⚙️ Chỉ chạy trong worker** (không import FastAPI)

| File | Trách nhiệm |
|---|---|
| `messaging/models.py` | `inbound_messages` (`UNIQUE(channel, message_id)` để chống trùng, `status`, `attempts`, `error`) và `outbound_messages` |
| `messaging/queue.py` | `enqueue` (api gọi) · `claim_next` (`FOR UPDATE SKIP LOCKED`) · đánh dấu `done`/`failed` · retry |
| `messaging/dispatcher.py` | Phân loại tin theo thứ tự: chưa liên kết → luồng mã mời · không phải text → nhắc gõ chữ · lệnh hệ thống (`OK` `Sai` `Hủy` `Tồn …` `Hướng dẫn` `Báo cáo`) · `Nhập`/`Xuất` → parser · còn lại: manager → `qa`, staff → hướng dẫn cú pháp |
| `parser/regex.py` | Cú pháp chuẩn `Nhập\|Xuất [SL] [ĐV] [nguyên liệu] [giờ] [ngày]`, chấp nhận không dấu, viết tắt |
| `parser/ner.py` | Nạp `model_quantized.onnx` một lần (ONNX Runtime), gán nhãn BIO: `ACTION QTY UNIT ITEM TIME DATE` |
| `parser/llm.py` | Fallback Gemini structured output theo schema cố định, validate bằng Pydantic |
| `parser/service.py` | `parse(text)`: regex → NER (nếu đủ confidence) → LLM; trả `ParsedAction` + `parser_source` |
| `parser/validate.py` | Nguyên liệu có trong danh mục (kể cả alias), đơn vị quy đổi được, SL > 0, xuất không vượt tồn, `event_time` không ở tương lai và ≤ 7 ngày |
| `qa/service.py` · `tools.py` · `prompts.py` | Q&A cho manager: LangChain + Gemini tool calling với tool viết sẵn (`get_stock`, `get_movements`, `top_items`, `staff_activity`), fallback SQL agent chỉ SELECT. Chạy bằng DB role `qa_reader` (read-only, `statement_timeout` 5s, ≤ 200 dòng). Trả lời tiếng Việt ≤ 2.000 ký tự |

### 7.6 Luồng xử lý một tin nhắn (map ra file)

```mermaid
sequenceDiagram
  participant Z as Zalo
  participant R as channels/router.py
  participant Q as messaging/queue.py
  participant W as worker.py
  participant D as messaging/dispatcher.py
  participant P as parser/service.py
  participant V as parser/validate.py
  participant L as inventory/ledger.py
  participant C as inventory/confirm.py
  participant A as channels/zalo.py
  Z->>R: POST /webhooks/zalo + secret header
  R->>Q: ZaloAdapter → InboundMessage → enqueue (ON CONFLICT DO NOTHING)
  R-->>Z: 200 ngay
  W->>Q: claim_next (FOR UPDATE SKIP LOCKED)
  W->>D: route(message)
  D->>P: "Nhập/Xuất ..."
  P->>V: ParsedAction
  alt parser_source = regex
    V->>L: ghi inventory_log
  else NER / LLM
    V->>C: tạo pending_actions, hỏi "OK / Sai"
  end
  D->>A: send_text (zalo_client.sendMessage)
  W->>Q: mark done / failed
```

`OK` → `confirm.py` chuyển pending thành dòng `inventory_log` + lưu `training_samples` (verified).
Pending không trả lời sau 10 phút → tự hủy. `Hủy` trong 30 phút → `ledger.py` tạo **dòng bù trừ** (`reverses_id`).

### 7.7 Dữ liệu: bảng → module sở hữu

| Bảng | Module | Ghi chú |
|---|---|---|
| `admins` | `auth` | Đăng nhập dashboard (tạo bằng `scripts/create_admin.py`) |
| `staff`, `invite_codes` | `staff` | Danh tính = `zalo_user_id` / `zalo_chat_id`, liên kết bằng mã mời (Zalo không gửi SĐT) |
| `items`, `units` | `items` | Danh mục + quy đổi đơn vị (seed: `scripts/seed_items.py`) |
| `inbound_messages`, `outbound_messages` | `messaging` | Hàng đợi + log gửi |
| `pending_actions`, `inventory_log`, view `current_stock` | `inventory` | `inventory_log` là **nguồn sự thật**, chỉ INSERT |
| `training_samples` | `labels` | Dữ liệu flywheel cho NER |

Migration: Alembic (`alembic/versions/`, hiện chưa có migration nào). Thời gian lưu `timestamptz`, múi giờ `Asia/Ho_Chi_Minh`.

### 7.8 Quy tắc ranh giới (bắt buộc)

- Domain gọi nhau qua `service`/`schemas`, **không** import `router` của domain khác.
- `messaging/`, `parser/`, `qa/` không import FastAPI.
- Chỉ `channels/` biết payload Zalo; mọi code sau đó chỉ thấy `InboundMessage`.
- Sổ cái `inventory_log` **append-only**: sửa = thêm dòng bù trừ, không bao giờ UPDATE/DELETE.
- Chỉ kết quả **regex** được ghi sổ trực tiếp; NER/LLM phải có `OK` của người gửi.
- Webhook trả 200 nhanh và chỉ enqueue; không log token Zalo; Q&A chạy trên DB role chỉ đọc; bot trả lời tiếng Việt.
- Không đổi `custom_generate_unique_id` trong `main.py` (làm hỏng client TypeScript của dashboard).

### 7.9 Thư mục ngoài `app/`

| Thư mục | Vai trò |
|---|---|
| `tests/` | pytest, cấu trúc giống `app/` (`test_health`, `test_webhook`, `test_parser`, `test_inventory`); `conftest.py` dùng chung |
| `alembic/` | `env.py` + migration |
| `ml/` | Pipeline NER (không deploy): `build_catalog` → `generate_synthetic` → `train_ner` (ViDeBERTa) → `evaluate` → `export_onnx` (int8). Dữ liệu thô trong `ml/data/` |
| `models/` | File `.onnx` worker nạp (gitignored, kéo từ HF Hub) |
| `scripts/` | `create_admin.py`, `seed_items.py`, `zalo_poll.py` (dev, `getUpdates`), `zalo_set_webhook.py` (`setWebhook` + secret). Polling và webhook loại trừ nhau |
| `.github/workflows/ci.yml` | `ruff` + `pytest` trên PR / push `main` |
| `.claude/` | Spec, system-design, ADR, rule cho Claude Code |

---

## 8. Dashboard (UI) gọi API ở đâu

| # | File | Vai trò |
|---|---|---|
| 1 | `app/main.py` | CORS (`CORS_ORIGINS`), mount `api_router` với prefix `/api` |
| 2 | `app/api.py` | Gom router của các domain UI dùng |
| 3 | `app/<domain>/router.py` | Endpoint cụ thể, vd `GET /api/stock` ở `app/inventory/router.py` |
| 4 | `app/auth/dependencies.py` | `get_current_user`: kiểm tra JWT cho router cần đăng nhập |
| 5 | `/api/openapi.json` | Repo web sinh client TypeScript (xem dưới) |

| Route | Ai gọi | File |
|---|---|---|
| `/api/auth/*` | Dashboard | `app/auth/router.py` |
| `/api/items/*` | Dashboard | `app/items/router.py` |
| `/api/staff/*` | Dashboard | `app/staff/router.py` |
| `/api/stock`, `/api/transactions/*` | Dashboard | `app/inventory/router.py` |
| `/api/labels/*` | Dashboard | `app/labels/router.py` |
| `/api/reports/*` | Dashboard | `app/reports/router.py` |
| `/api/chat/*` | Web chat demo | `app/chat/router.py` |
| `/webhooks/zalo` | **Zalo** (không phải UI) | `app/channels/router.py` |
| `/health` | Docker / CI | `app/main.py` |

**Sinh client TypeScript cho dashboard** (chạy trong repo web, khi API đang chạy):

```bash
npx @hey-api/openapi-ts -i http://localhost:8000/api/openapi.json -o src/client
```

Backend đổi API → chạy lại lệnh trên.

---

## 9. Train model NER

Xem chi tiết ở [`ml/README.md`](ml/README.md). Tóm tắt:

```bash
# Cài torch bản CUDA trước, theo hướng dẫn ở https://pytorch.org/get-started/locally/
pip install -e ".[ml]"
```

Thư viện ML **không** đóng vào image Docker; service chỉ cần file `.onnx` trong `models/`.

---

## 10. Xử lý lỗi thường gặp

| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| `requires a different Python: 3.14.x not in '<3.14,>=3.11'` | venv tạo bằng Python 3.14 | Xóa `.venv`, tạo lại bằng 3.11–3.13: `py -0p` → `py -3.13 -m venv .venv` |
| `.venv\Scripts\activate cannot be loaded because running scripts is disabled` | PowerShell chặn script | Chạy 1 lần: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `py install` / `py list` báo *legacy py.exe* | Máy dùng Python Launcher cũ | Dùng `py -0p` để xem bản đã cài, cài thêm từ python.org nếu thiếu |
| `fastapi : The term 'fastapi' is not recognized` | Chưa kích hoạt venv | `.venv\Scripts\activate` rồi chạy lại |
| `connection refused` tới Postgres | DB chưa chạy | `docker compose up -d postgres` |

---

## 11. Quy trình đóng góp

1. Tạo nhánh từ `main`: `git checkout -b feat/<ten-ngan>`
2. Code + test: `ruff check . --fix` và `pytest` phải pass
3. Commit theo dạng `feat: ...`, `fix: ...`, `docs: ...`
4. Push và mở Pull Request vào `main`; CI (`.github/workflows/ci.yml`) tự chạy lint + test
