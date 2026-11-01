# storagemate-service

Backend của **Storagemate**: AI agent ghi nhận nhập/xuất kho cho cửa hàng F&B từ tin nhắn Zalo, tính tồn kho real-time và trả lời câu hỏi của quản lý.

- **API** (FastAPI): webhook Zalo + REST API cho dashboard
- **Worker**: xử lý hàng đợi tin nhắn, parser (regex → NER → LLM), báo cáo định kỳ
- **PostgreSQL**: sổ cái nhập/xuất (append-only), hàng đợi, danh mục
- **ML**: train NER tiếng Việt (ViDeBERTa → ONNX), không deploy

## Mục lục

1. [Yêu cầu](#1-yêu-cầu)
2. [Cài đặt từng bước](#2-cài-đặt-từng-bước)
3. [Chạy bằng Docker Compose](#3-chạy-bằng-docker-compose)
4. [Lệnh thường dùng](#4-lệnh-thường-dùng)
5. [Biến môi trường](#5-biến-môi-trường)
6. [Cấu trúc thư mục](#6-cấu-trúc-thư-mục)
7. [Dashboard (UI) gọi API ở đâu](#7-dashboard-ui-gọi-api-ở-đâu)
8. [Train model NER](#8-train-model-ner)
9. [Xử lý lỗi thường gặp](#9-xử-lý-lỗi-thường-gặp)
10. [Quy trình đóng góp](#10-quy-trình-đóng-góp)

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

Kết quả mong đợi: `2 passed`.

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

## 7. Dashboard (UI) gọi API ở đâu

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

## 8. Train model NER

Xem chi tiết ở [`ml/README.md`](ml/README.md). Tóm tắt:

```bash
# Cài torch bản CUDA trước, theo hướng dẫn ở https://pytorch.org/get-started/locally/
pip install -e ".[ml]"
```

Thư viện ML **không** đóng vào image Docker; service chỉ cần file `.onnx` trong `models/`.

---

## 9. Xử lý lỗi thường gặp

| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| `requires a different Python: 3.14.x not in '<3.14,>=3.11'` | venv tạo bằng Python 3.14 | Xóa `.venv`, tạo lại bằng 3.11–3.13: `py -0p` → `py -3.13 -m venv .venv` |
| `.venv\Scripts\activate cannot be loaded because running scripts is disabled` | PowerShell chặn script | Chạy 1 lần: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `py install` / `py list` báo *legacy py.exe* | Máy dùng Python Launcher cũ | Dùng `py -0p` để xem bản đã cài, cài thêm từ python.org nếu thiếu |
| `fastapi : The term 'fastapi' is not recognized` | Chưa kích hoạt venv | `.venv\Scripts\activate` rồi chạy lại |
| `connection refused` tới Postgres | DB chưa chạy | `docker compose up -d postgres` |

---

## 10. Quy trình đóng góp

1. Tạo nhánh từ `main`: `git checkout -b feat/<ten-ngan>`
2. Code + test: `ruff check . --fix` và `pytest` phải pass
3. Commit theo dạng `feat: ...`, `fix: ...`, `docs: ...`
4. Push và mở Pull Request vào `main`; CI (`.github/workflows/ci.yml`) tự chạy lint + test
