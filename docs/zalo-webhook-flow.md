# Luồng Zalo Bot webhook (Pha 0, chưa DB)

> Cập nhật: 2026-11-04 · Kiểm chứng thực tế qua ngrok cùng ngày.

## 1. Webhook là gì

Webhook là **API của mình** (`POST /webhooks/zalo`). Có tin nhắn mới thì **Zalo chủ động gọi vào**, mình không phải đi hỏi.

- Zalo chỉ gọi được **URL HTTPS public**. Khi dev trên máy thì mở cổng 8000 ra ngoài bằng ngrok:
  `https://decrease-sugar-morality.ngrok-free.dev → http://localhost:8000` (domain dev cố định của tài khoản ngrok free).
- Đăng ký URL với Zalo bằng `setWebhook` (script `scripts/zalo_set_webhook.py set`). Script ghép URL như sau:
  `PUBLIC_BASE_URL` (trong `.env`) + `/webhooks/zalo`.
- Webhook và polling **loại trừ nhau** phía Zalo: đã đặt webhook thì `getUpdates` không nhận tin nữa.

## 2. Hai token, hai chiều

| | Bot token (`ZALO_BOT_TOKEN`) | Secret token (`ZALO_WEBHOOK_SECRET`) |
|---|---|---|
| Ai tạo | Zalo cấp | **Mình tự đặt** (8–256 ký tự) |
| Chiều | **BE → Zalo** | **Zalo → BE** |
| Nằm ở đâu | Trong URL: `https://bot-api.zaloplatforms.com/bot<TOKEN>/<method>` | Header `X-Bot-Api-Secret-Token` trên mỗi POST Zalo gửi tới webhook |
| Dùng để | Zalo biết request đến từ chủ bot (gửi tin, setWebhook…) | FastAPI biết request **thật sự từ Zalo**, không phải người lạ biết URL |
| Ai kiểm tra | Zalo | FastAPI (`verify_zalo_secret`) |

Secret được đưa cho Zalo **một lần** lúc `setWebhook`. Từ đó Zalo tự gắn nó vào mọi request gửi tới webhook.
Không bao giờ log bot token, vì token nằm ngay trong URL. `ZaloClient` thay token bằng `***` trong mọi thông báo lỗi.

## 3. Thiết lập (làm một lần mỗi khi đổi domain)

1. Chạy `fastapi dev` để server lên ở cổng 8000. Kiểm tra: `curl.exe http://localhost:8000/health` → `{"status":"ok"}`.
2. Chạy `ngrok http 8000` (ngrok v3 trở lên).
3. Trong `.env`: `PUBLIC_BASE_URL` = domain ngrok, và có `ZALO_WEBHOOK_SECRET`.
4. Chạy `.venv/Scripts/python scripts/zalo_set_webhook.py set`. Kết quả đúng:

   ```json
   "verification": { "ok": true, "outcome": "webhook.ok" }
   ```

Lệnh phụ: `info` (xem webhook đang đặt), `test` (nhờ Zalo gửi thử, có hạn mức), `delete` (xoá webhook để chuyển sang polling).

## 4. Luồng một tin nhắn qua file và hàm

```
Zalo ──POST /webhooks/zalo──▶ router.verify_zalo_secret ──403 nếu sai
                                  │ đúng
                                  ▼
                          router.zalo_webhook
                          ├─ zalo.save_sample       (ghi payload thô)
                          ├─ zalo.parse_update      (JSON → InboundMessage)
                          ├─ BackgroundTasks.add_task(queue.process)
                          └─ trả 200 {"message":"Success"} ngay
                                  │ (chạy nền)
                                  ▼
                          queue.process
                          ├─ SeenCache.add_if_new   (chống trùng message_id)
                          ├─ ZaloClient.send_chat_action("typing")
                          ├─ dispatcher.handle      (chọn câu trả lời)
                          │    └─ _handle_text → _phieu_replies
                          │         └─ regex.parse_phieu → catalog.resolve → replies.summary
                          ├─ zalo.render            (cắt ≤ 2000 ký tự, thêm "📋 Chọn nhanh")
                          └─ ZaloClient.send_message ──▶ Zalo (dùng bot token)
```

### Bước 0 · Khởi động: `app/main.py`
- `lifespan`: tạo **một** `ZaloClient(ZALO_BOT_TOKEN, ZALO_API_BASE)`, lưu ở `app.state.zalo`, đóng khi tắt app.

### Bước 1 · Nhận và kiểm tra secret: `app/channels/router.py`
- Route: `POST /webhooks/zalo` (prefix `/webhooks`).
- `verify_zalo_secret` là dependency, chạy **trước khi đọc body**:
  - đọc header `X-Bot-Api-Secret-Token`;
  - so với `ZALO_WEBHOOK_SECRET` bằng `hmac.compare_digest` (so trong thời gian cố định, chống đoán dần);
  - secret chưa cấu hình (rỗng) → từ chối mọi request;
  - sai hoặc thiếu → **403**.
- `zalo_webhook`: lưu mẫu, parse payload, đẩy `process` vào `BackgroundTasks`, rồi trả **200** ngay.
  Payload không đọc được thì vẫn trả 200 (ghi log warning) để Zalo không coi là lỗi.

### Bước 2 · Đọc payload: `app/channels/zalo.py`
- `save_sample(payload, dir)`: nối payload vào `data/zalo_samples/YYYY-MM-DD.jsonl` (gitignored), dùng để đối chiếu field thật.
- `parse_update(payload)`: chấp nhận cả dạng webhook `{event_name, message}` lẫn dạng getUpdates `{ok, result}`. Kết quả là `InboundMessage` (`app/channels/base.py`).
  - `message.date` tính bằng **mili-giây** và được đổi sang múi giờ `settings.TZ`.
  - Loại sự kiện `event`: `text`, `image`, `sticker`, `voice`, `unsupported`, `other`.

### Bước 3 · Xử lý nền: `app/messaging/queue.py`
- `process(msg, sender)` không bao giờ raise:
  1. `SeenCache.add_if_new("zalo:<message_id>")`: đã thấy trong 1 giờ qua thì bỏ qua.
  2. `send_chat_action(chat_id, "typing")`.
  3. `dispatcher.handle(msg, now, PENDING)` trả về danh sách `Reply`.
  4. Mỗi `Reply` → `render` → `send_message` cho từng đoạn.
  5. Có lỗi thì log, rồi `_send_error` gửi "⚠️ Bot gặp lỗi, bạn gửi lại giúp mình nhé".
- `SEEN` (chống trùng) và `PENDING` (câu hỏi A/B/C, TTL 10 phút) nằm **trong RAM của tiến trình**.

### Bước 4 · Chọn câu trả lời: `app/messaging/dispatcher.py`
- `handle`: có câu hỏi A/B/C đang chờ thì xử lý câu trả lời trước. Sau đó phân loại theo loại sự kiện:
  - sticker / voice / khác → `replies.text_only`
  - ảnh có caption → đọc caption như phiếu; ảnh không caption → `replies.photo_only`
  - chữ → `_handle_text`
- `_handle_text`: `menu` / `1` / `2` / `3` / `hướng dẫn` → menu, mẫu Xuất, mẫu Nhập, hướng dẫn. Không khớp thì thử đọc phiếu, đọc không được thì `replies.unknown`.
- `_phieu_replies`: `regex.parse_phieu` → `catalog.resolve` từng dòng → `replies.summary`. Có dòng trùng thì thêm `replies.duplicate_question` và lưu vào `PENDING`.
- Toàn bộ câu chữ tiếng Việt nằm ở `app/messaging/replies.py`.

### Bước 5 · Gửi trả lời: `app/channels/zalo_client.py`
- `send_message(chat_id, text, parse_mode)` → `_call` → `_post`.
- `_post`: `POST https://bot-api.zaloplatforms.com/bot<TOKEN>/sendMessage`, dùng `httpx.AsyncClient` chung. Lỗi mạng được bọc lại và **xoá token** khỏi thông báo.
- `_call`: thử lại tối đa 3 lần khi gặp 403 / 408 / 429, backoff `0,5·2ⁿ` + jitter. Lỗi khác ném `ZaloApiError`. Riêng 401 có gợi ý "token sai hoặc đã reset".

## 5. Kết quả kiểm chứng thực tế (2026-11-04)

| Thử nghiệm | Kết quả |
|---|---|
| `setWebhook` lần đầu với `PUBLIC_BASE_URL` sai domain | `webhook.http.404`, vì ngrok không có tunnel cho domain đó |
| `setWebhook` với đúng domain ngrok | `webhook.ok` |
| Nhắn `menu` khi server đang chạy | ngrok ghi `POST /webhooks/zalo 200`, bot trả menu |
| Tắt `fastapi dev`, nhắn 2 tin | ngrok trả **502 Bad Gateway** cho Zalo, 2 request |
| Bật lại server, chờ vài phút | **Zalo không gửi lại**, tin nhắn lúc server tắt bị mất |
| `getWebhookInfo` / `deleteWebhook` khi chưa đặt webhook | Zalo trả 404 / 400 (script coi là "chưa có webhook") |

Hệ quả: Pha 0 chấp nhận mất tin khi server tắt. Pha DB cần server chạy liên tục. Webhook lúc đó chỉ enqueue vào DB, worker lấy ra rồi gọi đúng `process()`.

Lỗi `curl.exe` trên Windows khi gọi domain ngrok (`CRYPT_E_REVOCATION_OFFLINE`, `Connection was reset`) đến từ mạng hoặc antivirus phía máy dev và không ảnh hưởng Zalo. Khi đó kiểm tra bằng `localhost` và trang ngrok inspector http://127.0.0.1:4040.

## 6. So với polling (`scripts/zalo_poll.py`)

| | Webhook | Polling |
|---|---|---|
| Cơ chế | Zalo đẩy tin (push) | Mình hỏi `getUpdates(30s)` liên tục (pull), mỗi lần nhận 1 sự kiện |
| Cần URL public | Có (ngrok) | Không |
| Kiểm tra đầu vào | Secret header | Không cần, vì mình gọi Zalo bằng bot token |
| Chạy bằng | `fastapi dev` | `python scripts/zalo_poll.py` |
| Bật chế độ | `zalo_set_webhook.py set` | `zalo_set_webhook.py delete`, rồi chạy poll |

Hai đường **dùng chung lõi**: sau `parse_update`, cả hai cùng gọi `queue.process()`, nên bot trả lời giống hệt nhau.
Polling dùng làm phương án dự phòng khi không có ngrok, hoặc khi mạng chặn ngrok.
