# Storagemate — Spec: Mã mời — nhân viên nhập mã để được dùng bot / Phase 1 (FastAPI)

> **Mục tiêu:** Chat Zalo chưa gắn với nhân viên nào chỉ được làm một việc: gửi **mã mời**. Mã đúng (chưa dùng, chưa hết hạn,
> chưa thu hồi) → bot gắn chat vào hồ sơ nhân viên, chào bằng tên, gửi cú pháp; từ đó ghi phiếu như bình thường.
> Stub: chưa có dashboard → mã được tạo bằng `scripts/dev_db.py --invite "Tên"` (bỏ khi có API dashboard).
> Nguồn phạm vi: `docs/storagemate-proposal-plan-v2.md` § Luồng hệ thống 2 "Kết nối nhân viên bằng mã mời", § Roadmap (Pha 1: mã mời;
> Pha 4: khoá khi sai nhiều lần). Proposal và code lệch nhau → hỏi, không tự chọn.
>
> **Trạng thái:** ✅ xong — test Zalo (polling) I1–I6 đúng, owner xác nhận 2026-11-07 · Owner: Nash · Tạo: 2026-11-06 · Cập nhật: 2026-11-07 · Phase: 1
> **Trạng thái code:** `ruff check .` sạch; `pytest` 133 pass trên PostgreSQL 16 local, DB `storagemate_test` (2026-11-07).
>
> **Phụ thuộc:** spec `2026-11-06-phase1-db-ledger-spec.md` (hàng đợi + worker + nhánh "chưa liên kết" trong `app/messaging/queue.py`).
> **Trước khi viết code:** đọc `system-design/conventions.md`, `.claude/rules/python-fastapi.md`.

---

## 0. Quyết định đã chốt (brainstorm 2026-11-06)

**Owner đã chốt:**

| # | Câu hỏi | Quyết định |
|---|---|---|
| 1 | Ai tạo mã, mã đến tay nhân viên thế nào | **Manager tạo mã** cho nhân viên, **tự gửi** mã cho nhân viên qua tin nhắn riêng, dặn nhân viên nhắn mã cho bot. |
| 2 | Tạo mã ở đâu | **Về sau trên dashboard**. Hiện chưa có dashboard → **nạp mã mẫu** để dùng tạm. |
| 3 | Luật khoá "sai > 5 lần / 15 phút" | **Để sau** (Phase 4 như roadmap). |
| 4 | Bảng | Dùng **`invite_codes` có sẵn** trong migration `0001_init` — không thêm migration. |
| 5 | Thứ tự test | **Polling trước**, webhook sau (hai đường dùng chung hàng đợi + worker nên logic như nhau). |

**Quyết định của Claude (owner xem lại khi đọc):**

| # | Quyết định | Lý do |
|---|---|---|
| A | "Nạp mã mẫu" = lệnh `python scripts/dev_db.py --invite "Lan" [--role manager]`: tạo `staff` (kho tổng, **chưa gắn Zalo**) + 1 dòng `invite_codes`, in mã + hạn ra màn hình. | Đúng thứ tự dashboard sẽ làm (thêm nhân viên → có mã); sau này chỉ thay script bằng API. |
| B | Mã: 6 ký tự `A–Z0–9` ngẫu nhiên (`secrets`), **dùng 1 lần**, **hết hạn sau 24 giờ** (`INVITE_TTL`). Trùng mã (UNIQUE) → sinh lại. | Proposal § Luồng 2 + CHECK `^[A-Z0-9]{6}$` của migration. |
| C | Nhân viên gõ thường / có dấu cách (`k7p2 q9`) vẫn nhận: bỏ khoảng trắng, viết hoa rồi mới so. | Gõ trên điện thoại hay sai kiểu này. |
| D | Chat **đã gắn** gửi chuỗi giống mã → coi như tin thường (không đổi liên kết). | Tránh lỡ tay làm mất liên kết. |
| E | Mã của nhân viên `active = false` → từ chối như mã sai. | Nhân viên đã nghỉ không được vào lại. |
| F | Nhân viên đã gắn một chat khác mà nhận mã mới (đổi điện thoại) → mã mới **thay** chat cũ. | Manager tạo mã mới chính là ý "cho vào lại". |
| G | Không lưu đếm lần sai. Mỗi lần sai ghi `inbound_messages.route = 'invite_failed'` → Phase 4 đếm theo `chat_id` trong 15 phút, không cần cột mới. | Proposal có `failed_attempts` nhưng migration không có; tránh migration cho thứ chưa làm. |
| H | `--link-staff` của spec trước **giữ lại** làm đường tắt khi dev. | Không ảnh hưởng luồng thật. |
| I | Mã hợp lệ nhưng `zalo_chat_id` / `zalo_user_id` này đang nằm trên **hồ sơ nhân viên đã nghỉ** (`active = false`) → **chuyển liên kết**: xoá `zalo_chat_id`, `zalo_user_id` khỏi hồ sơ cũ rồi gắn vào hồ sơ mới, cùng transaction. Đang nằm trên hồ sơ **còn làm** (chỉ xảy ra với `zalo_user_id`, vì chat đã gắn thì không vào nhánh này) → từ chối như mã sai, log warning. | Người nghỉ rồi được nhận lại vẫn vào được; không để lỗi UNIQUE làm tin bị `failed`. |
| J | `--invite "Lan"`: đã có **đúng một** nhân viên tên đó (không phân biệt hoa thường) → dùng lại hồ sơ đó; chưa có → tạo mới; có nhiều hơn một → dừng, báo trùng tên. Mã mới **thu hồi** (`revoked_at = now`) mọi mã chưa dùng cũ của nhân viên đó. | Mỗi nhân viên chỉ có 1 mã còn hiệu lực; cấp lại mã (đổi điện thoại, mục F) làm được bằng cùng lệnh. Dashboard sau này kế thừa quy tắc này. |

---

## 1. Phạm vi

| Có trong bản này | Chưa làm (để spec sau) |
|---|---|
| ORM `InviteCode` map bảng có sẵn | Tạo / thu hồi mã trên dashboard (spec API dashboard) |
| Worker: chat chưa gắn + tin là mã hợp lệ → gắn `staff.zalo_chat_id`, `zalo_user_id`, `linked_at`; `invite_codes.used_at`; bot chào + gửi cú pháp | Khoá chat sau 5 lần sai / 15 phút (Phase 4) |
| Mã sai / hết hạn / đã dùng / đã thu hồi → bot từ chối, không gắn gì | QR / deeplink tới bot |
| Chat chưa gắn gửi thứ khác → bot nhắc "gửi mã mời" | Phân quyền manager (Q&A, báo cáo) |
| `scripts/dev_db.py --invite "Tên" [--role manager]` | Gửi mã tự động cho nhân viên (manager tự gửi) |

---

## 2. Cài đặt & chạy

Như spec DB-ledger mục 2 (PostgreSQL 16 local, seed, `--map-codes`). Thêm:

```powershell
python scripts/dev_db.py --invite "Lan"                 # in: Mã mời cho Lan: K7P2Q9 (hết hạn 07/11 21:30)
python scripts/dev_db.py --invite "Chị Hoa" --role manager
```

### 2.1 Test qua Zalo (polling) — từng bước

3 tab PowerShell ở thư mục repo: **A** gõ lệnh, **B** worker, **C** poll. Mỗi tab:

```powershell
.venv\Scripts\Activate.ps1
$env:DATABASE_URL="postgresql+psycopg://postgres:<mật khẩu>@127.0.0.1:5432/storagemate"
```

Tab A thêm `$env:PGPASSWORD="<mật khẩu>"` để `psql` khỏi hỏi mật khẩu. Đặt cho gọn:
`$psql = "C:\Program Files\PostgreSQL\16\bin\psql.exe"` rồi gọi `& $psql -U postgres -h 127.0.0.1 -d storagemate -c "…"`.

1. **Tab A — tạo mã:** `python scripts/dev_db.py --invite "Hoa"` → dòng đầu `DB: …/storagemate`, dòng sau
   `Mã mời cho Hoa: K7P2Q9 (hết hạn …)`. Chép mã.
2. **Tab A — gỡ tài khoản Zalo đang test khỏi hồ sơ cũ** (phải ra `UPDATE 1`):
   `update staff set zalo_chat_id = null, zalo_user_id = null where name = 'Nash'`
3. **Tab B:** `python -m app.worker` → `Worker khởi động…`.
4. **Tab C:** `python scripts/zalo_poll.py` → `Đang poll Zalo…`. Báo "Webhook đang bật" → `python scripts/zalo_set_webhook.py delete` rồi chạy lại.
5. **Gửi từ Zalo**, mỗi lần một tin, chờ bot trả lời:

| # | Gửi | Bot phải trả lời | `inbound_messages` status / route | Kết quả 2026-11-07 |
|---|---|---|---|---|
| I1 | `menu` | "🔒 … Gửi mã mời 6 ký tự…" | `ignored` / `unlinked` | ✅ |
| I2 | `ABC123` (mã không tồn tại) | "❌ Mã mời không đúng hoặc đã hết hạn…" | `done` / `invite_failed` | ✅ |
| I3 | mã ở bước 1, gõ thường + dấu cách (`k7p 2q9`) | "Chào Hoa 👋 Bạn đã được kết nối với Kho tổng SG." + cú pháp | `done` / `invite_ok` | ✅ |
| I4 | (cùng chat) gửi lại đúng mã đó | "🤔 Mình chưa hiểu tin này…" (tin thường) | `done` / `other` | ✅ |
| I5 | (tài khoản Zalo thứ hai) gửi mã đã dùng | "❌ Mã mời không đúng hoặc đã hết hạn…" | `done` / `invite_failed` | ✅ (cũng phủ bằng `test_invalid_codes_rejected_with_same_reply[used]`) |
| I6 | (chat đã gắn) `ngày DD/MM nhập hàng về kho tổng` + xuống dòng `Cà phê kem béo: 2` | tóm tắt + "✅ Đã ghi 1/1 dòng" | `done` / `phieu` | ✅ |

6. **Tab A — kiểm tra DB:**
   - `select id, left(text, 25) as text, status, route, error from inbound_messages order by id desc limit 6`
     → theo thứ tự I1→I6: `unlinked`, `invite_failed`, `invite_ok`, `other`, (`invite_failed`), `phieu`.
   - `select s.name, s.zalo_chat_id, s.linked_at, c.code, c.used_at, c.revoked_at from staff s join invite_codes c on c.staff_id = s.id order by c.id desc limit 3`
     → Hoa có `zalo_chat_id`, `linked_at`; mã có `used_at`.
7. **Trả tài khoản về hồ sơ cũ** (cũng là test cấp lại mã / đổi điện thoại, mục 0 F):
   gỡ khỏi Hoa (`update staff set zalo_chat_id = null, zalo_user_id = null where name = 'Hoa'`),
   `python scripts/dev_db.py --invite "Nash"`, gửi mã đó cho bot → "Chào Nash 👋".

Lỗi thì ghi lại: tin đã gửi, tin bot trả lời, kết quả bước 6, log đỏ ở tab B.

### 2.2 Test qua Zalo (webhook) — chạy lại 2.1 bằng đường webhook

Webhook và poll dùng chung hàng đợi + worker, nên bảng I1–I6 (và T1–T6 của spec DB-ledger mục 2.4) phải ra **y hệt**.
Thứ thay đổi chỉ là đường vào. 4 tab: **A** lệnh, **B** worker, **C** API, **D** ngrok (tab A–C set env như 2.1).

1. **Tab C (đang chạy poll thì Ctrl+C trước):** `fastapi dev` → mở `http://127.0.0.1:8000/health` ra `{"status":"ok"}`.
   Mở `http://127.0.0.1:8000/` ra `{"detail":"Not Found"}` là **đúng** — không có route `/`.
2. **Tab D:** `ngrok http --url=<domain ngrok cố định> 8000`. Domain phải trùng `PUBLIC_BASE_URL` trong `.env`.
3. **Tab A:** `python scripts/zalo_set_webhook.py set` → kết quả có `"outcome": "webhook.ok"`.
   - `webhook.http.404` = sai domain / ngrok chưa chạy · `webhook.http.403` = `ZALO_WEBHOOK_SECRET` của API khác lúc `set` (khởi động lại tab C).
   - Tab C in warning `Bỏ qua payload Zalo không đọc được (event_name=webhook.test)` — **đúng**, sự kiện xác minh không vào hàng đợi.
   - `python scripts/zalo_set_webhook.py info` → `url` = `<domain>/webhooks/zalo`.
4. **Tab B:** `python -m app.worker`.
5. **Tab A:** chuẩn bị như 2.1 bước 1–2 (`--invite "Hoa"` cấp mã mới, mã cũ tự thu hồi; gỡ Zalo khỏi Nash).
6. **Gửi từ Zalo** W1–W6 = I1–I6 ở 2.1 (cùng tin, cùng câu trả lời, cùng `status`/`route`). Thêm:

| # | Làm | Phải thấy | Kết quả |
|---|---|---|---|
| W7 | Mỗi tin ở W1–W6 | ngrok inspector `http://127.0.0.1:4040`: `POST /webhooks/zalo` → `200`, thời gian vài chục ms (chỉ enqueue) | |
| W8 | Tab A: `curl.exe -s -o NUL -w "%{http_code}" -X POST http://127.0.0.1:8000/webhooks/zalo -H "Content-Type: application/json" -d "{}"` | in `403` (không có secret), không thêm dòng `inbound_messages` | |
| W9 | Tắt tab B (worker), gửi `menu`, rồi bật lại tab B | webhook vẫn `200`; tin nằm `pending` đến khi worker chạy lại → bot trả lời muộn | |
| W10 | (Tuỳ chọn) T1 + T3 của spec DB-ledger | như bảng 2.4 bên đó | |

7. **Tab A — kiểm tra DB:** câu `select` ở 2.1 bước 6 → route theo thứ tự như 2.1.
8. **Xong → về polling:** `python scripts/zalo_set_webhook.py delete` (không xoá thì `zalo_poll.py` từ chối chạy).

Test tự động cho đường này: `tests/test_webhook.py` (403 sai/thiếu secret, 200 + enqueue, trùng `message_id` 1 dòng,
`webhook.test` không vào hàng đợi, body không phải object → 422).

Dependency mới: **không** (`secrets` là stdlib). Biến môi trường mới: **không**.

---

## 3. Cấu trúc thư mục

```
app/staff/models.py        # + InviteCode (sửa)
app/staff/service.py       # + create_invite(), redeem_invite() (sửa)
app/messaging/queue.py     # nhánh chưa gắn → redeem / nhắc mã (sửa)
app/messaging/replies.py   # + invite_needed(), invite_rejected(), welcome() (sửa)
scripts/dev_db.py          # + --invite, --role (sửa)
tests/test_invite.py       # (mới)
```

---

## 4. Data model & migration

**Không có migration mới.** Bảng có sẵn (`0001_init`):

| Bảng | Cột dùng | Ràng buộc có sẵn |
|---|---|---|
| `invite_codes` | id, tenant_id, staff_id, code, expires_at, used_at, revoked_at, created_at | `code` UNIQUE + CHECK `^[A-Z0-9]{6}$`; FK `staff_id` |
| `staff` | zalo_user_id, zalo_chat_id, linked_at, active, role | UNIQUE `(tenant_id, zalo_user_id)`; UNIQUE `zalo_chat_id` (khi khác NULL) |

Mã hợp lệ = `code` khớp **và** `used_at IS NULL` **và** `revoked_at IS NULL` **và** `expires_at > now` **và** `staff.active`.
Đọc mã bằng `SELECT … FOR UPDATE` để hai tin cùng mã không gắn hai lần (dù chỉ có 1 worker).

---

## 5. Hợp đồng API

Không có endpoint mới. Webhook / poll không đổi — vẫn chỉ enqueue.

---

## 6. Tích hợp Zalo Bot

- Lấy `zalo_user_id` từ `inbound_messages.sender_id` (= `from.id` của Zalo), `zalo_chat_id` từ `chat_id`.
- Tin trả lời tiếng Việt, soạn ở `replies.py`. Không log mã mời ở mức INFO (log chỉ "chat X nhập mã sai/đúng").

---

## 7. Luồng xử lý & quy tắc nghiệp vụ

```
worker claim tin → tìm staff theo chat_id
  ├─ có (active) → dispatcher như cũ (spec DB-ledger)
  └─ không có:
       text bỏ khoảng trắng + viết hoa khớp ^[A-Z0-9]{6}$ ?
         ├─ không → reply invite_needed()           · status=ignored, route=unlinked
         └─ có → redeem_invite(session, code, chat_id, sender_id, now)
                  ├─ mã hợp lệ → staff.zalo_chat_id/zalo_user_id/linked_at; invite.used_at = now
                  │              reply welcome(staff) (chào tên + cú pháp)   · status=done, route=invite_ok
                  └─ không hợp lệ → reply invite_rejected()                   · status=done, route=invite_failed
COMMIT → gửi reply (như spec DB-ledger)
```

- Gắn chat + đánh dấu mã đã dùng nằm **cùng transaction** với cập nhật `inbound_messages`.
- Mã chưa tồn tại / hết hạn / đã dùng / thu hồi / nhân viên nghỉ → **cùng một câu trả lời** (không cho đoán mã nào có thật).
- `welcome(staff)`: "Chào {tên} 👋 Bạn đã được kết nối với {tên kho}." + cú pháp (dùng lại `help_text()` / menu hiện có).
- Chat / `zalo_user_id` đang nằm trên hồ sơ khác: hồ sơ đã nghỉ → chuyển liên kết; hồ sơ còn làm → từ chối như mã sai (mục 0 I).
  Kiểm tra trước khi UPDATE để không dính lỗi UNIQUE (`staff_zalo_chat_id_key`, `staff_tenant_id_zalo_user_id_key`).
- Không có job nền mới.

Cập nhật `system-design/data-flow.md` § 2 (linking) cho khớp route + câu trả lời.

---

## 8. Bảo mật & vận hành

- Mã sinh bằng `secrets.choice` (không dùng `random`). 36^6 ≈ 2,2 tỷ tổ hợp; chưa có khoá chống dò (Phase 4) → chấp nhận cho dev.
- Không log mã đầy đủ; không trả lời khác nhau giữa "mã không có" và "mã hết hạn".
- Chat chưa gắn **không** đi vào dispatcher → không ghi được gì vào sổ.

---

## 9. Code từng file

Code nằm thẳng trong repo:

| File | Nội dung |
|---|---|
| `app/staff/models.py` | + `InviteCode` |
| `app/staff/service.py` | `normalize_code()`, `create_invite()` (thu hồi mã cũ, `secrets`), `redeem_invite()` + `_release_from_former_staff()` (mục 0 I) |
| `app/messaging/queue.py` | `_handle_unlinked()`; route `unlinked` / `invite_ok` / `invite_failed` |
| `app/messaging/replies.py` | `invite_needed()` (thay `not_linked()`), `invite_rejected()`, `welcome()` |
| `scripts/dev_db.py` | `invite()` + cờ `--invite`, `--role` (mục 0 J) |
| `tests/test_invite.py`, `tests/test_dev_db.py` | 7 ca luồng + 5 ca mã không hợp lệ + chuẩn hoá mã + script |

---

## 10. Test

| Loại | File | Kiểm tra gì |
|---|---|---|
| DB | `tests/test_invite.py` | `test_valid_code_links_chat_and_marks_code_used`, `test_code_is_case_and_space_insensitive`, `test_invalid_codes_rejected_with_same_reply` (unknown / expired / used / revoked / inactive_staff), `test_unlinked_non_code_text_asks_for_code`, `test_unlinked_sticker_asks_for_code`, `test_linked_chat_sending_code_is_normal_text`, `test_new_code_relinks_staff_to_new_chat`, `test_chat_held_by_inactive_staff_moves_to_new_staff`, `test_zalo_user_of_active_staff_rejected`, `test_create_invite_revokes_previous_unused_code` |
| Unit | `tests/test_invite.py` | `test_normalize_code` (6 ca) |
| DB | `tests/test_dev_db.py` (sửa) | `test_invite_creates_unlinked_staff_and_valid_code`, `test_invite_same_name_reuses_staff_and_revokes_old_code` |
| DB | `tests/test_queue.py` (sửa) | ca "chưa liên kết" đổi câu trả lời |

---

## 11. Checklist nghiệm thu

- [x] I1–I6 ở mục 2.1 chạy đúng qua Zalo (polling) — owner xác nhận 2026-11-07
- [x] Sau I3: `staff.zalo_chat_id`, `linked_at` có giá trị; `invite_codes.used_at` có giá trị
- [x] Chat chưa gắn không tạo được dòng `inventory_log` nào (`test_unlinked_non_code_text_asks_for_code`)
- [x] Không log mã mời (log chỉ ghi chat_id / staff id); mọi tin bot gửi là tiếng Việt
- [x] `ruff check .` sạch, `pytest` 133 pass (có `TEST_DATABASE_URL`)
- [x] Cập nhật docs mục 12 + bump `last-updated`; đổi dòng `STATUS.md` sang ✅
- [ ] Test qua webhook (quyết định 5: sau polling) — để spec deploy / Phase 5
- [ ] Commit

---

## 12. System-design docs sẽ đổi

- `system-design/data-flow.md` — § 2 linking: route `unlinked` / `invite_failed` / `invite_ok`, câu trả lời, chưa có khoá.
- `system-design/database-design.md` — `invite_codes` đã dùng; tạo mã dev bằng `dev_db.py --invite`.
- `system-design/directory-map.md` — `staff/service.py` có `create_invite` / `redeem_invite`.

---

## 13. Nguồn tham khảo

| Thư viện / hệ thống | Version | Nguồn | Đã dùng cho mục |
|---|---|---|---|
| Python `secrets` | 3.13 stdlib | docs.python.org/3/library/secrets.html | 8 |
| SQLAlchemy | 2.1.6 | `with_for_update()` như spec DB-ledger | 4 |
