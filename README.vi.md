# Storagemate Service

[English](README.md) · **Tiếng Việt**

Backend của **Storagemate**, AI agent trên Zalo quản lý kho cho doanh nghiệp F&B.
Nhân viên báo nhập/xuất bằng cách nhắn tin tiếng Việt cho bot Zalo. Bot ghi mọi lần nhập/xuất vào sổ kho chỉ-thêm
(append-only), và quản lý có thể hỏi bot về tồn kho bằng câu hỏi thông thường. Dashboard web
(repo riêng `storagemate-ui`) đọc cùng dữ liệu qua REST API.


## Mục lục

1. [Tính năng](#1-tính-năng)
2. [Kiến trúc](#2-kiến-trúc)
3. [Cài đặt và chạy](#3-cài-đặt-và-chạy)
4. [Bật hỏi đáp cho quản lý](#4-bật-hỏi-đáp-cho-quản-lý)
5. [Lệnh thường dùng](#5-lệnh-thường-dùng)
6. [Biến môi trường](#6-biến-môi-trường)
7. [Cấu trúc thư mục](#7-cấu-trúc-thư-mục)
8. [Xử lý lỗi thường gặp](#8-xử-lý-lỗi-thường-gặp)
9. [Quy trình đóng góp](#9-quy-trình-đóng-góp)

---

## 1. Tính năng

| Tính năng | Cách hoạt động | Trạng thái |
|---|---|---|
| Bot Zalo | Polling (`scripts/zalo_poll.py`, cho máy dev) hoặc webhook có header bí mật | ✅ polling đã test trên Zalo · webhook chưa test trên Zalo |
| Hàng đợi tin | Bảng Postgres, bỏ qua webhook gửi trùng, đúng 1 worker | ✅ |
| Liên kết nhân viên | Nhân viên mới gửi mã mời 6 ký tự để gắn chat Zalo. Dùng 1 lần, không hết hạn | ✅ |
| Ghi phiếu từ tin nhắn | Regex đọc cú pháp chuẩn và ghi thẳng. Gemini đọc tin viết tự do; nhân viên phải trả `OK` thì mới ghi | ✅ regex · 🟡 LLM: xong code, chờ test trên Zalo |
| AI agent hỏi đáp cho quản lý | LangChain + Gemini gọi 5 tool chỉ đọc, chạy trên login Postgres chỉ đọc riêng | 🟡 xong code, đúng 12/12 câu hỏi mẫu, chờ test trên Zalo |
| API cho dashboard | Các endpoint đọc dưới `/api` (tồn kho, giao dịch, KPI tổng quan, hàng hoá, kho) | ✅ chỉ đọc, chưa có đăng nhập |
| Chưa làm | Model NER (mới có pipeline train trong `ml/`), lệnh `Hủy`, báo cáo định kỳ, đăng nhập admin (JWT), duyệt nhãn | 🔲 |

## 2. Kiến trúc

Một Docker image, hai process. Hai process **chỉ nói chuyện qua PostgreSQL** (không Redis hay Celery, xem ADR 0003).

```mermaid
flowchart LR
  zalo[Zalo Bot API] -->|POST /webhooks/zalo| api
  dash[Dashboard SPA] -->|GET /api/*| api
  subgraph image[storagemate-service image]
    api[api: FastAPI]
    worker[worker: python -m app.worker]
  end
  api -->|INSERT ... ON CONFLICT DO NOTHING| db[(PostgreSQL)]
  worker -->|SELECT ... FOR UPDATE SKIP LOCKED| db
  worker -->|login qa_reader: chỉ các view qa_*| db
  worker -->|sendMessage| zalo
  worker --> gemini[Gemini API]
```

### Một tin nhắn được xử lý thế nào

1. **api** kiểm tra secret của webhook, lưu tin vào `inbound_messages` rồi trả `200` ngay.
   `UNIQUE(channel, external_id)` bỏ qua webhook Zalo gửi lại lần hai.
2. **worker** lấy tin kế tiếp bằng `FOR UPDATE SKIP LOCKED` và xử lý trong **một transaction**.
3. Chat chưa liên kết → luồng mã mời. Chat đã liên kết → thử regex trước.
4. Regex đọc được → ghi vào sổ kho `inventory_log` (chỉ thêm; sửa sai bằng một dòng bù trừ mới).
5. Regex không đọc được → gọi Gemini một lần để phân loại tin là phiếu kho, câu hỏi hay thứ khác:
   - **phiếu kho** → lưu bản chờ, chỉ ghi sổ khi nhân viên trả `OK` (trong 10 phút);
   - **câu hỏi** của **quản lý** → AI agent hỏi đáp; của nhân viên thường → từ chối lịch sự;
   - **thứ khác** → "chưa hiểu" kèm hướng dẫn cú pháp.
6. Bot trả lời trên Zalo **chỉ sau khi transaction đã commit**.

### AI agent hỏi đáp cho quản lý (`app/qa/`)

Vòng lặp gọi tool tự viết bằng LangChain (`bind_tools`) và Gemini:

- Gemini chọn tool (`FindItems`, `GetStock`, `GetMovements`, `TopItems`, `StaffActivity`); code kiểm tra tham số bằng
  Pydantic, chạy SQL rồi trả kết quả. Gemini không bao giờ chạm vào database.
- Tối đa 5 lượt và 30 giây cho một câu hỏi. Có lỗi thì không trả lời, thay vì đưa ra con số bịa.
- Nhiều lớp bảo vệ: các tool kết nối bằng login riêng `qa_reader`, chỉ đọc, mỗi truy vấn tối đa 5 giây và chỉ đọc
  được 4 view soạn sẵn (không đọc bảng gốc, không thấy dữ liệu cá nhân). View không trả dòng nào nếu phiên chưa đặt
  tenant, nên lỡ quên lọc doanh nghiệp thì thấy rỗng chứ không lộ dữ liệu. Tenant và ngày hôm nay lấy từ code, không bao giờ từ model.

Chi tiết: [`.claude/system-design/`](.claude/system-design/README.md) (luồng dữ liệu, thiết kế DB, ADR trong `decisions/`).
Phạm vi nghiệp vụ: [`docs/storagemate-proposal-plan-v2.md`](docs/storagemate-proposal-plan-v2.md).

## 3. Cài đặt và chạy

### Yêu cầu

| Công cụ | Phiên bản | Ghi chú |
|---|---|---|
| Python | **3.11–3.13** | Không dùng 3.14 (`pyproject.toml` chặn; thư viện ML chưa hỗ trợ). Khuyên dùng 3.13 |
| PostgreSQL | 16 trở lên | Cài trên máy hoặc chạy bằng Docker |
| Token bot Zalo | | Lấy từ Zalo Bot Creator, để nhắn với bot |
| Gemini API key | | Lấy từ Google AI Studio, cho parser LLM và hỏi đáp. Không bắt buộc: thiếu thì bot chỉ dùng regex |

### Các bước

```bash
git clone https://github.com/kimmich04/storagemate-service.git
cd storagemate-service

# Windows: py -3.13 -m venv .venv ; .venv\Scripts\activate
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env            # Windows: copy .env.example .env  → rồi điền (mục 6)
```

**Database.** Tạo một database trống, trỏ `DATABASE_URL` vào đó, rồi chạy:

```bash
alembic upgrade head
```

Dữ liệu mẫu tháng 10/2026 (`dataset/seed.sql`, không có trong git, được gửi riêng) xoá và dựng lại schema ở bản
`0001_init`, nên nạp file này trước rồi mới chạy `alembic upgrade head`:

```bash
psql "<DATABASE_URL bỏ +psycopg>" -v ON_ERROR_STOP=1 -f dataset/seed.sql
alembic upgrade head
```

**Chạy** (ba cửa sổ terminal):

```bash
fastapi dev                     # api: http://127.0.0.1:8000/docs
python -m app.worker            # worker
python scripts/zalo_poll.py     # chỉ máy dev: kéo tin từ Zalo (không dùng chung với webhook)
```

**Gắn tài khoản Zalo của bạn:** tạo mã mời rồi gửi mã đó cho bot.

```bash
python scripts/dev_db.py --invite "Tên bạn" --role manager
```

Sau đó gửi thử một phiếu, ví dụ `ngày <dd/mm> nhập hàng về kho tổng` + xuống dòng `Cà phê kem béo: 5`
(ngày trong vòng 7 ngày gần nhất; cũ hơn sẽ bị từ chối).

### Test

```bash
pytest
```

Test cần một database **riêng** trong `TEST_DATABASE_URL`; database này **bị xoá sạch mỗi lần chạy**, nên đừng bao
giờ trỏ vào database dev. Để trống thì các test cần DB bị bỏ qua. Lần chạy đủ gần nhất: 218 pass (2026-11-15).
CI (`.github/workflows/ci.yml`) chạy `ruff` và `pytest` trên Postgres 16 cho mọi PR và mỗi lần push lên `main`.

## 4. Bật hỏi đáp cho quản lý

Hỏi đáp chỉ bật khi có cả Gemini lẫn login chỉ đọc. Code **không bao giờ** dùng `DATABASE_URL` thay vào.

1. `alembic upgrade head` tạo role `qa_reader` (chưa đăng nhập được) và các view `qa_*`.
2. Bằng tài khoản chủ database, bật đăng nhập một lần với mật khẩu ngẫu nhiên, không trùng mật khẩu khác:
   ```sql
   ALTER ROLE qa_reader WITH LOGIN PASSWORD '<mật khẩu ngẫu nhiên>';
   ```
   Sinh mật khẩu: `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
3. Trong `.env`: `DATABASE_URL_READONLY=postgresql+psycopg://qa_reader:<mật khẩu>@<host>:5432/<db>`, **cùng database** với `DATABASE_URL`.
4. Khởi động lại worker. Log phải có dòng `Hỏi đáp (Q&A): bật`.
5. Thử không cần Zalo: `python scripts/qa_ask.py --tenant 1 "Kho tổng còn bao nhiêu cà phê kem béo?"`

Chỉ nhân viên có role `manager` mới hỏi được.
Nếu URL hoặc mật khẩu sai, log vẫn báo đã bật; khi đó câu hỏi nào bot cũng trả "chưa hiểu".

## 5. Lệnh thường dùng

| Việc | Lệnh |
|---|---|
| Chạy API (tự reload) | `fastapi dev` |
| Chạy worker | `python -m app.worker` |
| Kéo tin từ Zalo (máy dev) | `python scripts/zalo_poll.py` |
| Đăng ký webhook Zalo | `python scripts/zalo_set_webhook.py` |
| Tạo mã mời | `python scripts/dev_db.py --invite "Tên" [--role manager]` |
| Hỏi AI agent từ dòng lệnh | `python scripts/qa_ask.py --tenant 1 "câu hỏi"` |
| Test | `pytest` |
| Lint + tự sửa / format | `ruff check . --fix` · `ruff format .` |
| Áp migration | `alembic upgrade head` |
| Migration mới | `alembic revision -m "ten_ngan"`, rồi tự viết (không dùng autogenerate, xem `database-design.md`) |

## 6. Biến môi trường

Khai báo trong `.env` (mẫu: `.env.example`), đọc bởi `app/config.py`. **Không commit `.env`.**

| Biến | Dùng cho | Mặc định / ví dụ |
|---|---|---|
| `DATABASE_URL` | Database chính của app (đọc và ghi) | `postgresql+psycopg://storagemate:storagemate@localhost:5432/storagemate` |
| `DATABASE_URL_READONLY` | Login `qa_reader` cho AI agent hỏi đáp. Để trống = tắt hỏi đáp | `postgresql+psycopg://qa_reader:***@localhost:5432/storagemate` |
| `TEST_DATABASE_URL` | Database riêng cho pytest, bị xoá mỗi lần chạy. Để trống = bỏ qua test DB | |
| `ZALO_BOT_TOKEN` | Token Zalo Bot API (nằm trong URL, không bao giờ ghi log) | |
| `ZALO_WEBHOOK_SECRET` | Kiểm tra ở mọi lần gọi webhook | chuỗi ngẫu nhiên ≥ 32 ký tự |
| `PUBLIC_BASE_URL` | URL public cho webhook | `https://<ten>.ngrok-free.app` |
| `GEMINI_API_KEY` · `LLM_MODEL` | Gemini cho parser LLM và hỏi đáp. Để trống = tắt cả hai | |
| `LLM_TIMEOUT_SECONDS` | Thời gian chờ tối đa một lần gọi Gemini | `15` |
| `PENDING_TTL_MINUTES` | Thời hạn trả `OK` cho phiếu do LLM đọc | `10` |
| `QA_TIMEOUT_SECONDS` · `QA_MAX_STEPS` | Giới hạn cho một câu hỏi | `30` · `5` |
| `WORKER_POLL_SECONDS` | Worker ngủ bao lâu khi hàng đợi rỗng | `1.0` |
| `INVITE_REUSABLE` | **Chỉ máy dev**: mã mời dùng lại được. Không bật ở production | `false` |
| `JWT_SECRET` · `DEV_AUTH_ENABLED` | Xác thực dashboard (chưa làm đăng nhập) | |
| `CORS_ORIGINS` | Domain của dashboard, phân cách bằng dấu phẩy | `http://localhost:5173` |
| `HF_MODEL_REPO` · `NER_MODEL_PATH` | Model NER (chưa dùng) | |
| `TZ` | Múi giờ | `Asia/Ho_Chi_Minh` |

Sinh chuỗi ngẫu nhiên: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

## 7. Cấu trúc thư mục

Chia theo domain (FastAPI "Bigger Applications" + fastapi-best-practices): mỗi domain có `router` · `schemas`
· `models` · `service` (+ `dependencies`, `exceptions` khi cần).

```
app/
├── main.py · api.py      # tạo app, CORS, mount /api và /webhooks
├── config.py · database.py · models.py · exceptions.py
├── worker.py             # process worker
├── channels/             # ⚡ webhook Zalo, adapter, Zalo client (code duy nhất biết payload Zalo)
├── messaging/            # ⚙️ hàng đợi (enqueue/claim), phân luồng, câu trả lời của bot
├── parser/               # ⚙️ regex → Gemini (structured output); NER chưa làm
├── inventory/            # sổ kho, bản chờ OK, API tồn kho + giao dịch 🖥️
├── qa/                   # ⚙️ AI agent hỏi đáp: vòng lặp, tool chỉ đọc, prompt
├── staff/                # nhân viên, tenant, kho, mã mời
├── items/ · locations/ · dashboard/   # 🖥️ API cho dashboard
└── auth/ · labels/ · reports/ · chat/ # khung sẵn cho các pha sau
alembic/versions/         # migration (SQL viết tay)
scripts/                  # dev_db, zalo_poll, zalo_set_webhook, qa_ask, create_admin
tests/                    # pytest trên Postgres thật
ml/                       # pipeline train NER (không deploy)
.claude/                  # spec, thiết kế hệ thống, ADR
```

🖥️ dashboard gọi · ⚡ Zalo gọi · ⚙️ chỉ chạy trong worker

**Quy tắc:** sổ kho chỉ thêm · webhook chỉ đưa tin vào hàng đợi · chỉ kết quả regex được ghi không cần `OK` ·
hỏi đáp chỉ dùng login chỉ đọc · đúng một worker · bot trả lời bằng tiếng Việt ·
không đổi tên hàm route (dashboard sinh client TypeScript từ `/api/openapi.json`).

## 8. Xử lý lỗi thường gặp

| Lỗi | Cách sửa |
|---|---|
| `requires a different Python: 3.14.x` | Tạo lại `.venv` bằng Python 3.11–3.13 (trên Windows, `py -0p` liệt kê các bản đã cài) |
| PowerShell chặn `.venv\Scripts\activate` | Chạy một lần: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Không nhận lệnh `fastapi` | Kích hoạt venv trước |
| `connection refused` tới Postgres | Bật Postgres và kiểm tra `DATABASE_URL` |
| `password authentication failed for user "qa_reader"` | Chạy bước `ALTER ROLE ... WITH LOGIN PASSWORD` ở [mục 4](#4-bật-hỏi-đáp-cho-quản-lý) với đúng mật khẩu trong `.env` |
| Quản lý hỏi mà bot trả "chưa hiểu" | Xem log worker có dòng `Hỏi đáp (Q&A): bật` không, rồi xem [mục 4](#4-bật-hỏi-đáp-cho-quản-lý). Gemini giới hạn tần suất cũng gây lỗi này; hỏi lại sau ít giây |
| Mã mời bị từ chối | Mã chỉ dùng một lần; tạo mã mới sẽ huỷ mã cũ. Tạo mã mới bằng `scripts/dev_db.py --invite` |

## 9. Quy trình đóng góp

1. Tạo nhánh từ `main`: `git checkout -b feat/<ten-ngan>`.
2. Viết spec trong `.claude/specs/` trước khi code tính năng ([mẫu](.claude/specs/_TEMPLATE-spec-backend.md)).
3. `ruff check . --fix` và `pytest` phải pass.
4. Commit dạng `feat: …`, `fix: …`, `docs: …`, rồi mở pull request vào `main`; CI tự chạy lint và test.
