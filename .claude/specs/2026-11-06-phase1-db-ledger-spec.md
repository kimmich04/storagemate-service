# Storagemate — Spec: Nối DB — hàng đợi tin + ghi sổ kho từ phiếu regex / Phase 1 (FastAPI)

> **Mục tiêu:** Tin Zalo của nhân viên được lưu vào `inbound_messages` (chống trùng), worker lấy ra xử lý, và các dòng
> phiếu nhập/xuất đọc được bằng regex được **ghi thật vào `inventory_log`** của kho tổng (quy về đơn vị gốc, chặn tồn âm).
> Dòng nào không ghi được thì bot nói rõ trong tin xác nhận để nhân viên gõ lại. Sổ bắt đầu từ **tồn cuối 31/10 trong Excel T10**.
> Thay 2 chỗ tạm của Phase 0: `BackgroundTasks` → hàng đợi Postgres; `SeenCache` RAM → `ON CONFLICT`.
> Stub còn giữ: nhân viên được gắn `zalo_chat_id` bằng script — bỏ khi spec mã mời xong.
> Nguồn phạm vi: `docs/storagemate-proposal-plan-v2.md` § Roadmap theo pha (Pha 1), § Luồng hệ thống 3 "Xử lý một tin nhắn",
> § Mô hình dữ liệu, § Cú pháp tin nhắn & Hybrid parser (validate). Proposal và code lệch nhau → hỏi, không tự chọn.
>
> **Trạng thái:** 🟡 code xong, chưa thử với Zalo thật · Owner: Nash · Tạo: 2026-11-06 · Cập nhật: 2026-11-06 · Phase: 1
> **Trạng thái code:** đã chạy `ruff check .` + `pytest` pass — 111 test, có DB (2026-11-06)
>
> **Cách dùng file:** mỗi mục `### \`đường/dẫn\`` ở mục 9 là một file: tạo đúng đường dẫn đó và dán nguyên khối code.
>
> **Trước khi viết:** tra context7 (resolve library id → fetch docs) cho **mọi** thư viện dùng trong spec
> (FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, psycopg 3, openpyxl), đúng version trong `pyproject.toml`. Ghi lại ở mục 13.
> Đọc trước: `system-design/conventions.md`, `.claude/rules/python-fastapi.md`, `system-design/database-design.md`.

---

## 0. Quyết định đã chốt (brainstorm 2026-11-06)

**Owner đã chốt:**

| # | Câu hỏi | Quyết định |
|---|---|---|
| 1 | Proposal 1 cửa hàng vs migration có `tenants`/`locations` | Theo **migration `0001_init`**. |
| 2 | Tồn đầu kỳ lấy ở đâu (dashboard đang là dữ liệu mẫu) | Số liệu **Excel T10 kho tổng SG**, nạp qua **seed `seed_t10_2026.sql`** của owner (mục 0 G) — nguồn: (`ml/data/Copy of Khanh - SG - THÁNG 10 - …xlsx`), sheet đầu tiên, cột I `Tồn cuối 31.10`. |
| 3 | Phiếu có dòng bot không đọc được | **Ghi các dòng đọc được ngay**; dòng không đọc được **không ghi**, tin xác nhận nói rõ dòng đó *chưa có trong sổ và dashboard*. Phase 2: dòng đó chuyển NER/LLM + `OK`. |
| 4 | Trong lúc chưa có NER (Phase 1) | Nhân viên **tự gõ lại dòng thiếu thành một phiếu ngắn mới**. |
| 5 | Dashboard (repo `storagemate-dashboard`) gọi data | **Spec riêng, làm sau spec này**: 5 endpoint khớp `src/api/types.ts` + login. Không nằm trong spec này. |
| 6 | Phase 1 có ghi sổ thật của nhân viên không | **Không — chỉ test trên DB dev.** Vì vậy không cần script sửa sai (dòng đảo) ở spec này. |
| 7 | Khoảng 01/11 → hôm nay không có phiếu thật | **Sinh nhập/xuất ảo không làm đổi số lượng**: script tạo các cặp IN + OUT cùng món, cùng số lượng, rải theo ngày 01/11 → hôm nay. `current_stock` vẫn đúng bằng tồn cuối 31.10; dashboard có dữ liệu để vẽ. |
| 8 | Lọc mặt hàng theo loại | Lấy loại từ **dòng tiêu đề nhóm trong Excel** ghi vào `items.category` (cột + index đã có). Excel T10 có 4 nhóm: `MERCHANDISE` (dòng 4–92), `HÀNG SẢN XUẤT` (94–116), `HÀNG CHI PHÍ CHUNG` (118–121), `HÀNG NGUYÊN VẬT LIỆU` (123–129). Bộ lọc trên dashboard làm ở spec API dashboard. |
| 9 | DB dev chạy ở đâu | **PostgreSQL 16 cài trên Windows** (service `postgresql-x64-16`, cổng 5432), **không dùng Docker** cho DB dev. Seed `seed_t10_2026.sql` nạp bằng `psql -f` (mục 2.2). |

**Quyết định của Claude (owner xem lại khi đọc):**

| # | Quyết định | Lý do |
|---|---|---|
| A | Sổ chỉ theo dõi **tồn kho tổng**. Mọi dòng ghi có `location_id` = `staff.default_location_id` (kho tổng). Nơi kia (220 / PQ / đối tác / nhà cung cấp) chỉ là `counterpart_location_id`. | Excel chỉ có tồn kho tổng; test đối soát cũng tính mọi phiếu Nhập vào "TỔNG NHẬP". Khớp `database-design.md` (OUT + counterpart, không `TRANSFER`). |
| B | Tên nơi kia không khớp `locations` → vẫn ghi, `counterpart_location_id = NULL` (chữ gốc còn trong `raw_message`). | Không vì thiếu nơi nhận mà mất cả phiếu; tồn kho tổng vẫn đúng. |
| C | `"nội bộ"`, `"đối tác"`, `"Dinh"` = cùng một location `kind='partner'`. | `test_reconcile.py` xếp chung sheet "XUẤT CHO ĐỐI TÁC-NỘI BỘ". |
| D | Dòng "bộ" → ghi **từng thành phần** (`ResolvedLine.components`), không ghi mã bộ. | `test_reconcile.py:80` tính như vậy và khớp Excel. |
| E | Dòng bị trả lại **không lưu riêng**: regex là tất định, Phase 2 parse lại `inbound_messages.text` là ra đúng các dòng đó. Đánh dấu bằng `inbound_messages.route = 'phieu_partial'`. | Không cần cột/bảng mới; dashboard sau này đếm `retypeCount` từ `route`. |
| F | Không ghi `outbound_messages` / `training_samples` (migration chưa có bảng). | Cần migration mới → spec sau. |
| G | ~~Viết `scripts/import_opening.py`~~ → **owner đã có seed `seed_t10_2026.sql`** (06/11): dùng seed, script nạp Excel chuyển vào `scripts/_archive/`. Seed để `items.code` NULL → `scripts/dev_db.py --map-codes` gán code = id cho id 1–123 (= MÃ VT kho tổng; đã kiểm 123/123 tên + tồn khớp Excel). Alias kho trong seed có dấu → ledger so bằng `fold()`. | Không viết lại thứ owner đã có. |
| H | Phiếu chốt sau câu trả lời A/C: các dòng ghi trỏ về **tin phiếu gốc** (`inbound_id`, `raw_message` = text phiếu gốc), `route` đặt trên tin gốc; tin trả lời "a"/"c" có `route='phieu_answer'`. `PendingQuestion.origin` giữ `InboundMessage` của tin gốc. | Phase 2 parse lại `text` của tin gốc mới ra đúng các dòng bị trả lại (mục 0 E). |
| I | Dòng bộ: **một thành phần vượt tồn → cả dòng bộ bị trả lại** (không ghi lẻ cốc mà thiếu đĩa). | Sổ phải khớp hàng thật đã gửi đi. |
| J | Dòng ảo (mục 0 #7): `parser_source='manual'`, `admin_id` = admin nhập liệu, `note='DỮ LIỆU ẢO (dev)'`; mỗi ngày chọn ngẫu nhiên vài món có tồn > 0, mỗi món 1 cặp: IN `q` lúc sáng rồi OUT `q` lúc chiều (`q` ≤ tồn, OUT luôn sau IN nên tồn không bao giờ âm). Seed cố định (`--seed`) để chạy lại ra cùng dữ liệu. Ghi thẳng bằng script, **không** qua `ledger.record()` (bỏ qua luật 7 ngày). | Lọc/xoá được dễ: DB dev `--reset` làm lại từ đầu; `note` cho biết dòng nào là ảo. Không đụng golden set. |
| L | Nhận dòng tiêu đề nhóm bằng **quy tắc**, không cố định số dòng: cột A trống + cột B có chữ → tiêu đề; mỗi mặt hàng lấy tiêu đề gần nhất phía trên. `category` lưu đúng chữ trong Excel (`MERCHANDISE`, `HÀNG SẢN XUẤT`, …). Món có trong catalog nhưng không có trong Excel → `category = NULL`. | Sheet tháng sau thêm/bớt dòng vẫn đọc đúng. |
| M | Catalog có tên trùng khác ĐVT («Bột kem trứng» mã 83 Gói / 118 Túi) mà DB bắt UNIQUE(tenant, lower(name)) → tên lưu DB của món sau thêm « (ĐVT)» (`app/items/service.db_names`). Ghi sổ tra theo `code`, không theo tên. | Phát hiện khi chạy test; không đổi catalog. |
| N | Tin xác nhận = **giữ bản tóm tắt** (bỏ dòng "🧪 Bản thử") **+ một tin kết quả ghi sổ** ("✅ Đã ghi x/y" + dòng chưa ghi). | Nhân viên vẫn thấy bot đọc phiếu thế nào; tin sau nói chắc cái gì đã vào sổ. |
| K | Lúc chạy thật (sau Phase 1) phải chọn lại ngày tồn đầu kỳ và **không** chạy `--fake-moves`. | Dữ liệu ảo chỉ hợp lệ trên DB dev (mục 0 #6). |

---

## 1. Phạm vi

| Có trong bản này | Chưa làm (để spec sau) |
|---|---|
| ORM model 2.0 cho bảng có sẵn: `tenants`, `locations`, `admins`, `staff`, `items`, `units`, `inbound_messages`, `inventory_log` | **API dashboard** (5 endpoint theo `types.ts`) + login JWT + lọc món theo `category` — spec kế tiếp |
| Webhook: `INSERT inbound_messages … ON CONFLICT (channel, external_id) DO NOTHING` → 200 (bỏ `BackgroundTasks`, bỏ `SeenCache`) | Mã mời / ghép tài khoản (`invite_codes`) |
| Worker: vòng lặp lấy tin `FOR UPDATE SKIP LOCKED`, xử lý, cập nhật `status` `done/failed/ignored`, `route`, `error` | Lệnh `Hủy` (dòng đảo `reverses_id`, 30 phút), `Tồn …` |
| Nhận diện người gửi theo `staff.zalo_chat_id`; chưa ghép → bot báo, `ignored` | `pending_actions` / OK·Sai, NER/LLM cho dòng bị trả lại (Phase 2) |
| `ledger.record()`: ghi từng dòng đọc được (`parser_source='regex'`), quy đổi `base_unit`, chặn tồn âm, kiểm thời gian; trả về dòng đã ghi + dòng bị trả lại kèm lý do | Báo cáo ngày/tháng |
| Tin xác nhận mới: "Đã ghi x/y dòng" + liệt kê dòng chưa ghi và lý do | Tra danh mục từ bảng `items` (vẫn dùng `catalog.json` trong RAM, chỉ map `code` → `items.id`) |
| `scripts/dev_db.py` (sau khi nạp seed): `--map-codes`, `--link-staff "Tên" <chat_id>`, `--fake-moves` (mục 0 J), `--reset` (chỉ DB localhost) | `outbound_messages`, `training_samples` (chưa có bảng) |
| | Script sửa sai bằng dòng đảo; chọn ngày tồn đầu kỳ cho lúc chạy thật (mục 0 K) |
| Hạ tầng test với Postgres thật (rollback mỗi test) + service Postgres trong CI | Web chat adapter |
| `scripts/zalo_poll.py` ghi vào hàng đợi thay vì gọi thẳng `process()` | Câu hỏi A/B/C dòng trùng vẫn giữ RAM (`PendingStore`) — xem mục 7 |

---

## 2. Cài đặt & chạy

Lệnh viết cho **PowerShell** trên Windows (máy owner). Mở 3 tab ở thư mục `storagemate-service`:
**A** gõ lệnh, **B** worker, **C** poll Zalo. Mọi tab đều phải bật venv **và** đặt `DATABASE_URL` (mục 2.2 bước 4).

### 2.1 Yêu cầu

| Thứ cần có | Ghi chú |
|---|---|
| Python 3.11–3.13 + venv `.venv` | `pip install -e ".[dev]"` |
| **PostgreSQL 16** cài trên Windows, service `postgresql-x64-16` chạy | DB dev (mục 0 #9). Bản 18 trên máy owner thiếu thư mục `bin` → không dùng được |
| Mật khẩu user `postgres` | để tạo user/DB cho app (quên → mục 2.6) |
| File seed `seed_t10_2026.sql` | dữ liệu T10, **chỉ có data, không có schema** → nạp SAU `alembic upgrade head` |
| `ZALO_BOT_TOKEN` trong `.env` | đã có từ Phase 0 |
| Zalo nhắn được với bot | để test mục 2.4 |

### 2.2 Dựng DB dev (làm 1 lần, tab A)

1. Bật PostgreSQL 16 (PowerShell **Run as administrator**):
```powershell
Start-Service postgresql-x64-16
```
2. Tạo user + database cho app (hỏi mật khẩu `postgres`):
```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -h 127.0.0.1 -p 5432 -c "CREATE ROLE storagemate LOGIN PASSWORD 'storagemate'" -c "CREATE DATABASE storagemate OWNER storagemate"
```
3. Bật venv:
```powershell
.venv\Scripts\Activate.ps1
```
4. Trỏ app vào DB (đổi user/mật khẩu/tên DB nếu dùng khác) — **làm ở cả 3 tab**:
```powershell
$env:DATABASE_URL="postgresql+psycopg://storagemate:storagemate@127.0.0.1:5432/storagemate"
```
5. Tạo bảng (phải chạy TRƯỚC khi nạp seed):
```powershell
alembic upgrade head
```
6. Nạp seed (`-f` đọc thẳng file → không lỗi mã hoá tiếng Việt; `-1` = một transaction, lỗi thì không ghi gì):
```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U storagemate -h 127.0.0.1 -p 5432 -d storagemate -v ON_ERROR_STOP=1 -1 -q -f "<đường dẫn>\seed_t10_2026.sql"
```
7. Kiểm tra seed — mong đợi `rev=0001_init`, `items=359`, `co_code=0`, `so_cai`≈1.200, `nhan_vien=0`:
```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U storagemate -h 127.0.0.1 -p 5432 -d storagemate -c "select (select version_num from alembic_version) rev, (select count(*) from items) items, (select count(code) from items) co_code, (select count(*) from inventory_log) so_cai, (select count(*) from staff) nhan_vien"
```
8. Gán `items.code` cho 123 món kho tổng (dòng đầu in `DB: …` để biết đang trỏ DB nào):
```powershell
python scripts/dev_db.py --map-codes
```
9. Gắn chat Zalo của mình làm nhân viên kho tổng (`chat_id` lấy ở mục 2.4 bước 1 nếu chưa biết):
```powershell
python scripts/dev_db.py --link-staff "Nash" <zalo_chat_id>
```
10. (Tuỳ chọn) dữ liệu ảo 01/11 → hôm qua, tồn không đổi:
```powershell
python scripts/dev_db.py --fake-moves --seed 1
```

Làm lại từ đầu: `python scripts/dev_db.py --reset` → lặp lại bước 6, 8, 9.

### 2.3 Chạy bot bằng polling (không cần ngrok)

1. Tab A — polling và webhook loại trừ nhau; có URL webhook thì xoá:
```powershell
python scripts/zalo_set_webhook.py info
```
```powershell
python scripts/zalo_set_webhook.py delete
```
2. Tab B — worker (đúng 1 tiến trình):
```powershell
python -m app.worker
```
3. Tab C — poll, phải in "Đang poll Zalo…":
```powershell
python scripts/zalo_poll.py
```

Chạy bằng webhook thay polling: `fastapi dev` + ngrok + `python scripts/zalo_set_webhook.py set` (như Phase 0); worker vẫn như bước 2.

### 2.4 Test qua Zalo

1. Chưa gắn chat: nhắn `menu` → bot trả "🔒 … chưa được liên kết" (đúng). Lấy `chat_id` rồi chạy mục 2.2 bước 9:
```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U storagemate -h 127.0.0.1 -p 5432 -d storagemate -c "select id, chat_id, sender_name, text, status, route from inbound_messages order by id desc limit 5"
```
2. Gửi lần lượt (mỗi dòng phiếu là một dòng tin; Zalo PC xuống dòng bằng Shift+Enter; `DD/MM` = hôm nay).
   Tồn đầu (seed, kho tổng): mã 1 = 696 hộp · mã 2 = 484 hộp · mã 4 Ly Espresso = 17 cái.

| # | Gửi | Bot phải trả lời | `inbound_messages.route` |
|---|---|---|---|
| T1 | `ngày DD/MM nhập hàng về kho tổng` · `Hộp cà phê trứng sấy thăng hoa: 2 thùng` · `Cà phê kem béo: 10` | tóm tắt + **✅ Đã ghi 2/2 dòng** | `phieu` |
| T2 | `ngày DD/MM nhập hàng về kho tổng` · `Cà phê kem béo: 5` · `xyz khong co: 3` | **✅ Đã ghi 1/2** + «xyz khong co: 3» — không tìm thấy món | `phieu_partial` |
| T3 | `ngày DD/MM xuất từ kho tổng sang kho 220` · `Ly Espresso: 999` | **Chưa ghi**: tồn Ly Espresso chỉ còn 17 cái | `phieu_rejected` |
| T4 | `ngày DD/MM nhập hàng về kho tổng` · `Cà phê kem béo: 2` · `Cà phê kem béo: 2` → trả lời `a` | hỏi A/B/C → **✅ Đã ghi 1/1**, số lượng 4 | tin phiếu `phieu`, tin `a` = `phieu_answer` |
| T5 | `ngày 20/10 nhập hàng về kho tổng` · `Cà phê kem béo: 1` | **Chưa ghi phiếu**: ngày 20/10 đã quá 7 ngày | `phieu_rejected` |
| T6 | gửi 1 sticker | "Mình chỉ đọc được tin nhắn chữ…" | `other` |

3. Kiểm tra sau mỗi ca (tab A) — dòng sổ vừa ghi, tồn, trạng thái tin:
```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U storagemate -h 127.0.0.1 -p 5432 -d storagemate -c "select l.id, l.action, i.code, i.name, l.qty, l.unit, l.qty_base, l.inbound_id from inventory_log l join items i on i.id = l.item_id where l.parser_source = 'regex' order by l.id desc limit 10"
```
```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U storagemate -h 127.0.0.1 -p 5432 -d storagemate -c "select i.code, i.name, s.qty_base from current_stock s join items i on i.id = s.item_id where s.location_id = 1 and i.code in ('1','2','4')"
```
```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U storagemate -h 127.0.0.1 -p 5432 -d storagemate -c "select id, left(text, 30) as text, status, route, error from inbound_messages order by id desc limit 10"
```
   Sau T1: mã 1 = **744** (696 + 48). Mọi tin `status = done` (sticker/người lạ: `ignored`), `error` trống.
4. Gặp lỗi → ghi lại: tin đã gửi · bot trả lời gì · dòng `inbound_messages` (status/route/error) · log đỏ ở tab B.

Lần chạy đầu của owner (06/11, DB nạp từ Excel): T1–T6 đều ra đúng `route` như bảng.

### 2.5 Chạy test tự động (pytest)

`TEST_DATABASE_URL` phải là **DB riêng**: fixture chạy `downgrade base` → `upgrade head` mỗi lần, **xoá sạch** DB đó. Không bao giờ trỏ vào DB dev.
```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -h 127.0.0.1 -p 5432 -c "CREATE DATABASE storagemate_test OWNER storagemate"
```
```powershell
$env:TEST_DATABASE_URL="postgresql+psycopg://storagemate:storagemate@127.0.0.1:5432/storagemate_test"
```
```powershell
ruff check .
```
```powershell
pytest
```
Không đặt `TEST_DATABASE_URL` → test DB bị skip (83 pass, 28 skip). Có đặt → 109 pass (06/11). CI tự dựng `postgres:16`.

### 2.6 Sự cố đã gặp khi dựng (06/11)

| Triệu chứng | Nguyên nhân | Cách sửa |
|---|---|---|
| pgAdmin "PostgreSQL 18": `connection timeout expired` | PG18 không có service, thiếu `bin\pg_ctl.exe` | dùng PG16 (hoặc cài lại PG18 bằng bộ cài EDB) |
| `Start-Service … Cannot open … service` | PowerShell không chạy quyền admin | mở PowerShell **Run as administrator** |
| `password authentication failed for user "postgres"` | quên mật khẩu `postgres` | (admin) sao lưu `pg_hba.conf` → đổi `scram-sha-256` thành `trust` → `Restart-Service postgresql-x64-16` → `ALTER USER postgres PASSWORD '…'` → **trả lại `pg_hba.conf` gốc** → restart |
| `zalo_poll.py` crash `port 5432 … password authentication failed for user "storagemate"`, bot im lặng | tab đó chưa đặt `DATABASE_URL` → app dùng giá trị mặc định | đặt `$env:DATABASE_URL` ở **mọi tab**; tin lúc crash đã mất (Zalo không gửi lại) → gửi lại |

Dependency mới: **không**.

| Gói | Version | Lý do |
|---|---|---|
| — | — | — |

Biến môi trường mới (khai báo trong `app/config.py` + `.env.example`; **không** đọc/commit `.env`):

| Biến | Bắt buộc | Mặc định | Ý nghĩa |
|---|---|---|---|
| `TEST_DATABASE_URL` | không | `""` | DB riêng cho pytest; trống → test DB bị skip (giống `real_messages`). CI luôn đặt. |
| `WORKER_POLL_SECONDS` | không | `1.0` | Hàng đợi rỗng thì ngủ bao lâu rồi hỏi lại |

---

## 3. Cấu trúc thư mục

```
app/
├── config.py                    # TEST_DATABASE_URL, WORKER_POLL_SECONDS (sửa)
├── worker.py                    # vòng lặp hàng đợi (sửa)
├── channels/router.py           # add_task → enqueue (sửa)
├── messaging/
│   ├── models.py                # InboundMessage ORM (mới)
│   ├── inbox.py                 # enqueue() + claim_next() + mark_done/failed/ignored() (mới)
│   ├── queue.py                 # bỏ SeenCache; process() dùng session + staff (sửa)
│   ├── dispatcher.py            # trả thêm phiếu đã chốt để ghi (sửa)
│   └── replies.py               # "đã ghi x/y" / dòng chưa ghi / "chưa liên kết" (sửa)
├── staff/models.py              # Tenant, Location, Staff ORM (mới)
├── staff/service.py             # find_by_chat_id() (mới)
├── auth/models.py               # Admin ORM — chỉ để làm actor cho dòng tồn đầu kỳ (mới)
├── items/models.py              # Item, Unit ORM (mới)
└── inventory/
    ├── models.py                # InventoryLog ORM (mới)
    └── ledger.py                # record(): validate từng dòng + INSERT (mới)
scripts/import_opening.py        # (mới)
scripts/zalo_poll.py             # gọi enqueue thay process (sửa)
tests/conftest.py                # fixture db_session (sửa)
tests/test_inbox.py, tests/test_ledger.py, tests/test_worker.py, tests/test_import_opening.py   # (mới)
.github/workflows/ci.yml         # service postgres:16 (sửa)
```

`Tenant`/`Location` đặt trong `staff/models.py` (cùng chỗ với `Staff` cần FK tới chúng) — quyết định của builder nếu thấy chỗ khác hợp hơn,
miễn cập nhật `directory-map.md`.

---

## 4. Data model & migration

**Không có migration mới** — mọi bảng đã có trong `0001_init`. Spec chỉ khai báo ORM **khớp đúng** bảng đó.

| Bảng | Cột ORM cần khai báo | Ghi chú |
|---|---|---|
| `tenants` | id, name, timezone | 1 dòng |
| `locations` | id, tenant_id, code, name, kind, aliases | xem bảng seed bên dưới |
| `admins` | id, tenant_id, email, name, password_hash | 1 dòng `import@storagemate.local`, `password_hash='!'` (không đăng nhập được) |
| `staff` | id, tenant_id, default_location_id, name, role, zalo_user_id, zalo_chat_id, active, linked_at | tra theo `zalo_chat_id` (partial unique index) |
| `items` | id, tenant_id, code, name, category, base_unit, min_qty | `code` = `CatalogItem.code` = Excel cột A `MÃ VT`; `category` = tiêu đề nhóm Excel (mục 0 #8, L) |
| `units` | id, item_id, unit_name, factor | từ `conversions` của catalog (bỏ factor `None`) |
| `inbound_messages` | toàn bộ cột | `external_id` = `InboundMessage.message_id` |
| `inventory_log` | toàn bộ cột | chỉ INSERT; trigger DB chặn UPDATE/DELETE |

**Locations seed** (`aliases` so bằng `fold()`):

| code | name | kind | aliases |
|---|---|---|---|
| `KT` | kho tổng | warehouse | kho tong, khi tong |
| `K220` | kho 220 | branch | 220, kho 220 |
| `PQ` | Phú Quốc | branch | pq, phu quoc |
| `DT` | đối tác / nội bộ | partner | doi tac, noi bo, dinh |

**Tồn đầu kỳ:** mỗi dòng Excel có `MÃ VT` khớp `items.code` và `Tồn cuối 31.10 > 0` → 1 dòng `inventory_log`:
`action='ADJUST'`, `parser_source='opening'`, `location_id`=KT, `qty = qty_base = tồn`, `unit = base_unit`, `delta_base = +tồn`,
`admin_id` = admin nhập liệu, `event_time = 2026-10-31 23:59:59+07:00`, `note='Tồn cuối 31.10 (Excel T10)'`.
Tồn = 0 → bỏ qua (CHECK `qty > 0`). Tồn âm → không nạp, in ra cảnh báo. Mã có trong Excel nhưng không có trong catalog → bỏ qua, in danh sách.

- Enum Postgres đã tồn tại → ORM dùng `Enum(..., name="inv_action", create_type=False)` (và tương tự các enum khác).
- `--autogenerate` **vẫn không chạy** (migration viết tay). Kiểm khớp schema bằng test: insert qua ORM vào DB đã `upgrade head`.
- Không thêm bảng mới → không cần cấp quyền read-only mới.
- Cập nhật `system-design/database-design.md`.

---

## 5. Hợp đồng API

| Method | Path | Auth | Request | Response | Mã lỗi |
|---|---|---|---|---|---|
| `POST` | `/webhooks/zalo` | header `X-Bot-Api-Secret-Token` | payload Zalo | `200` `{"message": "Success"}` | `403` sai secret |

- Hợp đồng ngoài **không đổi**; chỉ đổi bên trong: lưu + enqueue thay vì chạy `process()`.
- Tin trùng (`ON CONFLICT DO NOTHING` không trả dòng) → vẫn `200`, không làm gì.
- Lỗi DB khi INSERT → `500`. `integrations.md` đã xác minh 04/11: **Zalo không gửi lại** → tin đó mất (có log).
- Payload không đọc được (`parse_update` trả `None`) → giữ hành vi hiện tại: log warning, `200`, không enqueue.
- Endpoint cho dashboard: **không** ở spec này (xem mục 0 #5).

---

## 6. Tích hợp Zalo Bot / hệ thống ngoài

| Hệ thống | Hướng | Endpoint / phương thức | Xác thực | Timeout / retry |
|---|---|---|---|---|
| Zalo Bot | vào | `POST /webhooks/zalo` | `hmac.compare_digest` (giữ nguyên) | — |
| Zalo Bot | ra | `sendChatAction`, `sendMessage` qua `zalo_client.py` có sẵn | token trong URL | giữ cấu hình hiện tại |

- Webhook: sai secret → `403`, không lưu. Đúng → `save_sample` (giữ) + INSERT `inbound_messages` (`payload` = jsonb thô) → `200`.
- Worker giữ một `ZaloClient` dùng chung cho cả process; không log URL/token.
- Test: `tests/fakes.py` (sender giả), không gọi Zalo thật.

---

## 7. Luồng xử lý & quy tắc nghiệp vụ

```
Zalo → webhook (verify + save_sample + INSERT ON CONFLICT DO NOTHING, 200)
     → worker: BEGIN; claim 1 tin pending FOR UPDATE SKIP LOCKED
             → tìm staff theo chat_id ── không có/inactive → reply "chưa liên kết", status=ignored
             → dispatcher.handle() (giữ thuần logic) → replies + phiếu đã chốt (nếu có)
             → phiếu đã chốt → ledger.record() → INSERT các dòng ghi được → kết quả (đã ghi, bị trả lại + lý do)
             → reply xác nhận dựng từ KẾT QUẢ GHI; status=done, route, processed_at; COMMIT
     → sau COMMIT mới gửi replies qua Zalo
     → lỗi bất kỳ: ROLLBACK → transaction mới: status=failed, attempts+1, error → gửi replies.bot_error()
```

**Claim:** `select(InboundMessage).where(status == 'pending').order_by(received_at).limit(1).with_for_update(skip_locked=True)`.
Giữ khóa suốt transaction xử lý → worker chết giữa chừng thì rollback, tin tự về `pending`. Cột `locked_at`, `attempts` vẫn cập nhật để debug.
Gửi Zalo thất bại sau COMMIT → chỉ log (sổ đã đúng; không gửi lại để tránh ghi đôi).

**Phiếu "đã chốt"** = phiếu không còn nhóm dòng trùng chờ hỏi A/B/C. Câu hỏi A/B/C vẫn nằm trong `PendingStore` RAM:
chỉ có đúng 1 worker nên đúng; giới hạn: restart worker là mất câu hỏi đang chờ (nhân viên gửi lại phiếu). Trả lời "B" (gửi lại) → không ghi gì.
Tin hiện tại đang hỏi A/B/C → `route='phieu_waiting'`, chưa ghi.

**Quy tắc ghi (kiểm được bằng test):**
1. Chỉ `parser_source='regex'` ghi thẳng (non-negotiable). Spec này không có tầng NER/LLM.
2. **Từng dòng một** (mục 0 #3). Một dòng được ghi khi: `status == "ok"`, `item` khác `None`, `qty_base` khác `None`,
   và `base_unit == item.base_unit` (tức đã quy đổi được). Còn lại bị **trả lại** với lý do:
   `unknown` → "không tìm thấy món"; `ambiguous` → `warning` của resolver; chưa quy đổi đơn vị → `warning`;
   `bad_lines` → "không đọc được dòng này"; vượt tồn → câu tồn (quy tắc 6).
3. Mỗi dòng ghi → 1 bản ghi (dòng bộ → 1 bản ghi mỗi thành phần, mục 0 D): `qty`/`unit` như nhân viên gõ (thành phần: `qty_base`/`base_unit`),
   `qty_base`, `delta_base = +qty_base` (IN) / `-qty_base` (OUT), `action` = `Phieu.action`, `staff_id`, `inbound_id`,
   `raw_message` = text tin, `note` = `RawLine.note` và/hoặc `Phieu.date_note`.
4. Kho (mục 0 A–C): `location_id` = `staff.default_location_id`. `counterpart_location_id` = location khớp `to_loc` (OUT) / `from_loc` (IN)
   theo `fold(name)` hoặc `aliases`; không khớp hoặc `"?"` → `NULL`.
5. `event_time` = `Phieu.date` + giờ:phút của `sent_at` (múi `Asia/Ho_Chi_Minh`). Không ở tương lai, không quá 7 ngày trước `now` → nếu vi phạm,
   **cả phiếu** không ghi (ngày là của cả phiếu), bot báo ngày và hỏi gõ lại. Phiếu có `date_note` (sửa ngày "thật ra là") vẫn ghi bình thường.
6. OUT: tồn kho tổng của item (view `current_stock`) trừ dần theo thứ tự các dòng OUT cùng item trong phiếu; dòng làm tồn < 0 → bị trả lại:
   "⚠️ Tồn <tên> chỉ còn <x> <đv>, không thể xuất <y> <đv>." Các dòng sau vẫn xét tiếp. Dòng bộ: xét mọi thành phần trước,
   một thành phần thiếu → cả dòng bị trả lại (mục 0 I).
7. Ghi các dòng + cập nhật `inbound_messages` trong **một transaction**.
8. `route`: tất cả dòng ghi được → `'phieu'`; có dòng bị trả lại → `'phieu_partial'`; không dòng nào ghi được → `'phieu_rejected'`;
   không phải phiếu (menu, hướng dẫn, sticker…) → `'other'`.

**Tin xác nhận** (gửi sau bản tóm tắt, mục 0 N; tiếng Việt, `replies.ledger_result`):
```
✅ Đã ghi 9/10 dòng — XUẤT kho tổng → Phú Quốc, 05/11.
⚠️ Chưa ghi 1 dòng (CHƯA có trong sổ và dashboard):
• "30 túi mer nhỏ" — không tìm thấy món
Gõ lại dòng này thành phiếu mới, ví dụ: Xuất PQ 05/11
30 túi mer nhỏ
```
Không dòng nào ghi được → không có dòng "✅", chỉ liệt kê lý do.

**Trường hợp biên:** tin trùng (dedup ở INSERT); người lạ / staff `active=false` (ignored); sticker/ảnh/voice (dispatcher có sẵn);
số lượng 0 (bị trả lại, không để DB `CHECK` nổ); item có trong catalog nhưng chưa có trong bảng `items` → dòng bị trả lại "món chưa có trong danh mục DB"
(và log warning — nghĩa là chưa chạy import).

**Job nền:** không thêm. Worker là vòng lặp `asyncio` (vì `process()`/Zalo client async) gọi DB sync trực tiếp — chấp nhận được vì chỉ có
1 worker và không có việc nào khác trên event loop.

Cập nhật `system-design/data-flow.md`.

---

## 8. Bảo mật & vận hành

- Auth: webhook chỉ secret header (giữ). Không có endpoint mới.
- Ghi sổ chỉ qua ORM; `current_stock` đọc bằng `select()`/`text()` có bind param.
- `inventory_log` chỉ INSERT (trigger DB là lưới an toàn cuối).
- App dùng role chủ bảng (bypass RLS vì không `FORCE`) — đúng như migration. Q&A read-only không đụng.
- Log: không log full text tin ở INFO, không log token/URL Zalo. `error` lưu `repr(exc)` cắt ngắn; không gửi stack trace ra Zalo.
- Worker bắt `Exception` ở vòng lặp, `logger.exception`, `status=failed`, rồi xử lý tin sau (không chết cả worker).
- `import_opening.py`: từ chối nạp nếu đã có tenant (tránh nạp đôi tồn đầu kỳ); `--dry-run` in tổng kết không ghi gì.
  `--reset` dùng `TRUNCATE` (trigger append-only chỉ chặn UPDATE/DELETE, cố ý cho TRUNCATE) và từ chối nếu `DATABASE_URL` không trỏ `localhost`.
  File Excel là dữ liệu thật — không commit, không copy vào `tests/fixtures` đã commit.

---

## 9. Code từng file

Code nằm thẳng trong repo (không chép lại vào đây để khỏi lệch hai nơi). Danh sách file:

| File | Vai trò |
|---|---|
| `app/models.py` (sửa) | `type_annotation_map`: `int`→BigInteger, `str`→Text, `datetime`→timestamptz |
| `app/staff/models.py`, `app/staff/service.py` | `Tenant`, `Location`, `Staff`; `find_by_chat_id()` |
| `app/auth/models.py`, `app/items/models.py`, `app/items/service.py` | `Admin`; `Item`, `Unit`; `db_names()` (mục 0 M) |
| `app/messaging/models.py`, `app/messaging/inbox.py` | `InboundMessage` ORM; `enqueue` / `claim_next` / `find` / `to_message` / `finish` / `mark_failed` |
| `app/inventory/models.py`, `app/inventory/ledger.py` | `InventoryLog`; `record()` → `LedgerResult` |
| `app/messaging/dispatcher.py`, `pending.py`, `replies.py` (sửa) | `handle()` trả `Outcome`; `PendingQuestion.origin`; `ledger_result()`, `not_linked()` |
| `app/messaging/queue.py` (viết lại) | `process_next()`: 1 tin / 1 transaction, gửi sau COMMIT |
| `app/worker.py` (viết lại), `app/channels/router.py`, `app/main.py` (sửa) | vòng lặp worker; webhook enqueue; bỏ ZaloClient khỏi API |
| `app/config.py`, `alembic/env.py` (sửa) | `TEST_DATABASE_URL`, `WORKER_POLL_SECONDS`; env.py giữ URL do test đặt |
| `scripts/dev_db.py` (mới), `scripts/zalo_poll.py` (sửa) | sau khi nạp seed: map-codes / link-staff / fake-moves / reset; poll → enqueue. `scripts/_archive/import_opening.py` = bản nạp Excel cũ |
| `tests/conftest.py` + `test_inbox/ledger/queue/dev_db/webhook/scripts/dispatcher.py` | fixture DB (downgrade→upgrade mỗi lần chạy, SAVEPOINT mỗi test) |
| `.github/workflows/ci.yml` (sửa) | service `postgres:16` + `TEST_DATABASE_URL` |

Chưa làm được: thêm `TEST_DATABASE_URL` / `WORKER_POLL_SECONDS` vào `.env.example` (công cụ bị chặn đọc file `.env*`) — owner thêm tay.

Đã kiểm trên seed thật (DB nháp, 06/11): tồn kho tổng khớp cột "Tồn cuối 31.10" cho cả 123 mã; `--map-codes` gán 123 món;
2 phiếu chạy qua worker ghi đúng 3 dòng, trả lại đúng 2 dòng (món lạ, xuất vượt tồn), counterpart «nội bộ» khớp.

---

## 10. Test

| Loại | File | Kiểm tra gì |
|---|---|---|
| DB | `tests/test_inbox.py` | `test_enqueue_same_message_twice_inserts_one_row`, `test_claim_skips_row_locked_by_other_session` |
| DB | `tests/test_ledger.py` | `test_in_phieu_writes_one_row_per_line_in_base_unit`, `test_unknown_item_line_skipped_others_written`, `test_out_more_than_stock_skips_only_that_line`, `test_two_out_lines_same_item_checked_cumulatively`, `test_bundle_line_writes_components`, `test_unmatched_counterpart_written_with_null`, `test_event_time_older_than_7_days_writes_nothing` |
| DB | `tests/test_queue.py` (thay test cũ của `process()`) | `test_unlinked_chat_marked_ignored_and_gets_reply`, `test_handler_error_marks_failed_and_sends_bot_error`, `test_reply_sent_only_after_commit`, `test_partial_phieu_route_and_reply_lists_skipped_lines` |
| DB | `tests/test_import_opening.py` | workbook nhỏ dựng bằng openpyxl trong test (không dùng file thật): tồn đầu kỳ đúng, tồn 0 bỏ qua, mã lạ bỏ qua, chạy lần 2 bị từ chối; `test_item_category_from_nearest_group_header_above`; `test_fake_moves_leave_current_stock_unchanged`, `test_fake_moves_same_seed_same_rows` |
| API | `tests/test_webhook.py` (sửa) | 403 vẫn đúng; secret đúng → có dòng `inbound_messages`, không gọi `process()` |
| Golden set | `tests/test_reconcile.py` (giữ) | parser không đổi hành vi |

- Fixture `db_session`: engine theo `TEST_DATABASE_URL`, `alembic upgrade head` một lần mỗi session test,
  mỗi test chạy trong transaction ngoài + `join_transaction_mode="create_savepoint"` rồi rollback.
- Thiếu `TEST_DATABASE_URL` → skip test DB (local); CI **phải** có (service `postgres:16`).
- Test unit cũ (dispatcher, regex, catalog) giữ nguyên; test dispatcher sửa theo kiểu trả về mới.
- Coverage code mới ≥ 80%.

---

## 11. Checklist nghiệm thu

**Chức năng:**
- [ ] `import_opening.py` trên file Excel T10 → `current_stock` của kho tổng khớp cột `Tồn cuối 31.10` cho mọi mã có trong catalog
- [ ] Mọi món có trong Excel có `items.category` đúng nhóm (`SELECT category, count(*) FROM items GROUP BY 1` ra 4 nhóm)
- [ ] Sau `--fake-moves` → có dòng IN/OUT mỗi ngày từ 01/11, `current_stock` vẫn khớp cột `Tồn cuối 31.10`
- [ ] Gửi phiếu nhập kho tổng toàn món có trong catalog → đúng số dòng `inventory_log` IN, `qty_base` đúng, `parser_source='regex'`, bot "✅ Đã ghi n/n dòng"
- [ ] Phiếu 1 dòng sai tên món → các dòng khác vào sổ, bot liệt kê dòng chưa ghi + lý do, `route='phieu_partial'`
- [ ] Zalo gửi lại cùng `message_id` → `inbound_messages` vẫn 1 dòng, sổ không ghi đôi
- [ ] XUẤT vượt tồn → dòng đó không ghi, bot báo tồn còn lại
- [ ] Chat chưa có trong `staff` → bot báo chưa liên kết, `status='ignored'`
- [ ] Kill worker giữa chừng → tin quay về `pending`, chạy lại được, không ghi đôi

**Non-negotiables Storagemate:**
- [ ] `inventory_log` chỉ INSERT; sửa sai bằng dòng đảo
- [ ] Webhook trả 200 nhanh, chỉ lưu + enqueue; sai secret → 403
- [ ] Không log Zalo token / URL chứa token
- [ ] Q&A chạy trên role read-only (không đụng)
- [ ] Chỉ parse bằng regex mới ghi thẳng; NER/LLM cần `OK` của người gửi
- [ ] Vẫn chỉ đúng 1 worker
- [ ] Không đọc `.env` trong code/test/script
- [ ] Mọi tin bot gửi là tiếng Việt

**Chất lượng:**
- [ ] `ruff check .` và `ruff format --check .` sạch
- [ ] `pytest` pass (có `TEST_DATABASE_URL`), coverage code mới ≥ 80%
- [ ] `alembic upgrade head` rồi `alembic downgrade -1` chạy được trên DB trống
- [ ] `/docs` vẫn hiện đúng webhook

**Gate "done":**
- [ ] Cập nhật các file `system-design/` ở mục 12 + bump `last-updated` trong `system-design/README.md`
- [ ] Đổi dòng của spec này trong `STATUS.md` sang ✅

---

## 12. System-design docs sẽ đổi

- `system-design/data-flow.md` — §3a Phase 0 path → đã thay bằng hàng đợi; §3 luồng chính: claim/transaction/gửi sau commit, ghi từng dòng, `route`.
- `system-design/database-design.md` — ORM đã có; seed = `scripts/import_opening.py` (thay mô tả `import_excel.py`/`dataset/` không tồn tại); chỉ theo dõi tồn kho tổng.
- `system-design/api-contracts.md` — webhook giờ enqueue; tin trùng trả 200.
- `system-design/integrations.md` — Zalo có retry khi webhook 5xx không (nếu xác minh được).
- `system-design/directory-map.md` — `messaging/inbox.py`, chỗ đặt `Tenant`/`Location`, `scripts/import_opening.py`.
- `system-design/deployment.md` — CI có service Postgres; bước nạp tồn đầu kỳ khi dựng máy mới.

---

## 13. Nguồn tham khảo

context7 không có trong phiên làm việc này → API đối chiếu với **version đã cài trong `.venv`** và test chạy trên Postgres 16 thật.

| Thư viện / hệ thống | Version đã cài | Nguồn | Đã dùng cho mục |
|---|---|---|---|
| SQLAlchemy | 2.1.6 (`pyproject`: ≥2.0) | API 2.0: `with_for_update(skip_locked=True)`, `postgresql.insert().on_conflict_do_nothing()`, `postgresql.ENUM(create_type=False)`, `Session(join_transaction_mode="create_savepoint")` — kiểm bằng test | 4, 7, 10 |
| psycopg | 3.3.6 | driver | 2 |
| Alembic | 1.20.1 | `command.downgrade/upgrade` với `Config()` không đọc ini (tránh `fileConfig` tắt logger) | 10 |
| openpyxl | 3.1.5 | `load_workbook(read_only=True, data_only=True)` | 4 |
| FastAPI | 0.162.0 | `def` route + `Depends(get_db)` | 5 |
| Postgres `SKIP LOCKED` queue | 16 | https://www.dbpro.app/blog/postgresql-skip-locked · https://github.com/mattbillenstein/pg-queue | 7 |
| `ON CONFLICT DO NOTHING` không RETURNING dòng trùng | 16 | https://www.postgresql.org/message-id/CADyrUxMVOR-BjirpPptbFe4KeKuPuwoZaP7sigqe__CmLajkfg%40mail.gmail.com | 5 |
