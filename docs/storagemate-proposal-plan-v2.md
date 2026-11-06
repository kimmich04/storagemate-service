# Storagemate — Proposal Plan

> Bản Markdown của **Storagemate-Proposal-Plan v2** (file gốc: `Storagemate-Proposal-Plan.docx`, 2026-11-01).
> Đây là nguồn sự thật cho scope; bản tóm tắt cho agent nằm ở `.claude/system-design/`. Sửa scope → sửa file này trước.

Nov 1, 2026 · @Nash · v2: chuyển kênh nhắn từ WhatsApp sang Zalo Bot

## TL;DR

Storagemate là một AI agent chạy trên Zalo (Zalo Bot) giúp cửa hàng F&B ghi nhận nhập/xuất kho tự động từ tin nhắn của nhân viên và tổng hợp kiểm kê cuối tháng — thay cho việc quản lý soi tay từng dòng tin nhắn rồi nhập vào sheet.

mục tiêu: đi hết một vòng build full-stack + AI engineering end-to-end: ingestion → parser (regex + NER tự train) → database → Q&A agent → dashboard → vòng học lại.

**Thay đổi chính so với v1:**

- **Kênh:** WhatsApp Cloud API → Zalo Bot Platform (bot nhắn 1:1, tạo bằng Zalo Bot Creator, không cần Zalo OA). Nhân viên F&B ở Việt Nam đã có Zalo sẵn, không phải cài thêm app.
- **Định danh:** whitelist số điện thoại → ghép tài khoản bằng mã mời, vì payload của Zalo Bot không chứa số điện thoại.
- **Xác thực webhook:** chữ ký HMAC X-Hub-Signature-256 → secret token trong header X-Bot-Api-Secret-Token.
- **Ingestion:** webhook trả 200 ngay, lưu vào hàng đợi Postgres có chống trùng; container worker xử lý nền.
- **Thêm:** lớp channel adapter, trang web chat demo dùng chung pipeline, bước xác nhận OK/Sai cho tin do NER/LLM đọc, lệnh Hủy và sổ cái chỉ thêm (append-only).

## Problem

Nỗi đau chính nằm ở khâu tổng hợp kiểm kê cuối tháng, hiện làm hoàn toàn thủ công.

Quy trình thủ công hiện tại trong F&B:

- **Nhập hàng:** nhân viên nhắn vào nhóm chat theo mẫu Nhập [số lượng] [nguyên liệu] [thời gian], kèm hình.
- **Xuất hàng:** tương tự với Xuất [số lượng] [nguyên liệu] [thời gian], kèm hình.
- **Cuối tháng:** quản lý ngồi soi lại từng dòng tin nhắn trong nhóm, cộng trừ và nhập tay vào sheet kiểm kê.

Hệ quả: tốn nhiều giờ mỗi tháng, dễ sai số, không có tồn kho theo thời gian thực, và không biết nhân viên nào ghi sai cú pháp.

## Giải pháp & phạm vi

Storagemate nhận tin nhắn 1:1 qua Zalo Bot, bóc tách thành dữ liệu có cấu trúc, lưu database, xác nhận lại với nhân viên, và tự tạo báo cáo.

Scope đã chốt:

- **Kênh chính:** Zalo Bot Platform, mỗi nhân viên nhắn 1:1 với bot. Không dùng nhóm chat: tính năng nhóm của Zalo Bot còn đang thử nghiệm nội bộ, và khi ra mắt bot cũng chỉ nhận tin có @nhắc bot hoặc trả lời tin của bot.
- **Kênh phụ:** trang web chat trên dashboard, đi qua đúng pipeline như Zalo — dùng để demo, cho giám khảo gõ thử, và dự phòng khi Zalo trục trặc.
- **Không dùng Zalo OA:** cần xác thực doanh nghiệp, gói trả phí để mở API, và giới hạn thời gian gửi tin tư vấn (xem mục so sánh).
- **Parse:** hybrid — regex trước, NER tự train, rồi LLM fallback. Tin do NER/LLM đọc phải được nhân viên xác nhận OK trước khi ghi.
- **Ảnh:** Pha 1 bỏ qua ảnh (bot nhắc gõ nội dung bằng chữ); OCR hóa đơn để pha sau.
- **Model:** có train NER tiếng Việt trên Google Colab + vòng học lại (data flywheel).
- **Tồn kho:** tính real-time — mỗi lần ghi nhập/xuất là tồn cập nhật ngay, không chờ cuối tháng.
- **Phạm vi:** làm 1 cửa hàng cho ổn định trước; multi-tenant (nhiều cửa hàng) để sau.

Hai output cho người dùng: (1) xác nhận tức thì sau mỗi tin (hoặc báo lỗi cụ thể để gõ lại), (2) báo cáo cuối ngày và cuối tháng.

## Vì sao chọn Zalo Bot

| **Tiêu chí** | **WhatsApp Cloud API (v1)** | **Zalo OA** | **Zalo Bot (chọn)** |
|---|---|---|---|
| Người dùng tại VN | Ít; nhân viên phải cài thêm app | Dùng app Zalo có sẵn | Dùng app Zalo có sẵn |
| Thiết lập | Meta Business, số test, token 24h khi dev | Xác thực doanh nghiệp (thường 4–14 ngày), tạo app, xin quyền từng API | Tạo trong app Zalo vài phút; token gửi qua tin nhắn |
| Chi phí | Từ 1/10/2026 tính phí tin dịch vụ sau 1.000 tin/tháng/số | Cần gói Nâng cao/Premium (khoảng 99k–399k đ/tháng) để dùng API | Chưa thấy công bố phí (đang beta) |
| Giới hạn gửi tin | Cửa sổ 24h; ngoài cửa sổ phải dùng template | Tin tư vấn miễn phí trong 48h, tính phí đến 7 ngày, sau đó bị từ chối | Tài liệu không nêu cửa sổ thời gian — phải test thực tế ở Pha 0 |
| Xác thực webhook | HMAC X-Hub-Signature-256 | Chữ ký X-ZEvent-Signature | Secret token X-Bot-Api-Secret-Token |
| Token | System User token | OAuth; refresh token ~3 tháng, xoay vòng | Token tĩnh |
| Điểm trừ | Sai thị trường | Setup nặng, có phí | Beta, tối đa 3 bot/tài khoản, API không có nút bấm, nhóm chưa mở |

Rủi ro beta được giảm bằng lớp channel adapter: nếu Zalo Bot đổi luật, chỉ cần viết thêm adapter cho Zalo OA; router, parser và database không phải sửa.

## Kiến trúc hệ thống

Hệ thống gồm 7 khối:

- **Người dùng & kênh** — nhân viên/manager nhắn 1:1 với Zalo Bot; admin và giám khảo dùng web chat demo trên dashboard.
- **Ingestion (container api, FastAPI)** — nhận webhook, kiểm tra secret token, channel adapter chuẩn hóa tin, ghi vào inbound_messages (chống trùng theo message_id), trả 200 ngay.
- **Xử lý (container worker)** — lấy tin từ hàng đợi, nhận diện người gửi, router, parser cascade, validate, xác nhận, ghi sổ và gửi trả lời; chạy luôn lịch báo cáo; nạp model NER (ONNX).
- **Dữ liệu (PostgreSQL)** — sổ cái inventory_log là nguồn sự thật, view current_stock, hàng đợi, mẫu train.
- **Hỏi đáp & báo cáo** — LLM tool calling trên view chỉ đọc; báo cáo ngày/tháng gửi qua sendMessage.
- **Dashboard (React + Vite)** — admin quản lý nhân viên và mã mời, xem tồn, sửa giao dịch, duyệt nhãn, web chat demo.
- **Feedback & Retraining Loop** — mẫu đã xác nhận → Colab retrain NER → HF Hub → worker nạp version mới (data flywheel).

![Hình 1. Kiến trúc: luồng dữ liệu đi xuống qua 7 khối; nét đứt là vòng học lại đưa NER version mới về worker.](assets/figure-1.png)

*Hình 1. Kiến trúc: luồng dữ liệu đi xuống qua 7 khối; nét đứt là vòng học lại đưa NER version mới về worker.*

### Thành phần chạy thực tế

| **Thành phần** | **Lệnh chạy** | **Vai trò** |
|---|---|---|
| api | uvicorn app.main:app | Webhook Zalo, REST cho dashboard, web chat. Không xử lý nặng để luôn trả 200 nhanh. |
| worker | python -m app.worker | Cùng image với api. Đọc hàng đợi, parser (NER ONNX nạp trong process), gọi LLM, gửi tin, APScheduler. Chạy đúng 1 instance để job báo cáo không bị trùng. |
| postgres | PostgreSQL 16 | Dữ liệu + hàng đợi. Volume riêng, pg_dump định kỳ. |
| Dịch vụ ngoài | — | Zalo Bot API, LLM API, Hugging Face Hub, Vercel (web), ngrok (tunnel). |

So với v1, service ner riêng được gộp vào worker để còn 3 container. Có thể tách lại khi model lớn hoặc cần scale riêng.

## Luồng hệ thống

Hệ thống có 8 luồng: thiết lập bot (một lần), kết nối nhân viên, xử lý tin nhắn (luồng chính), xác nhận/hủy, hỏi đáp, báo cáo định kỳ, dashboard, và flywheel.

### 1. Thiết lập bot (một lần)

- Trên app Zalo (điện thoại): tìm OA **Zalo Bot Manager** → chọn **Tạo bot** → mở mini app **Zalo Bot Creator** → đặt tên bắt đầu bằng "Bot", ví dụ Bot Storagemate. Chỉ cần tài khoản Zalo cá nhân, không cần Zalo OA hay giấy tờ doanh nghiệp.
- Zalo gửi Bot Token (dạng 123456789:abc...) qua tin nhắn → lưu vào ZALO_BOT_TOKEN trong .env, không commit.
- Gọi getMe để kiểm tra token.
- Dev local: chạy scripts/zalo_poll.py (dùng getUpdates) — không cần URL public, xem được payload thật.
- Demo/production: bật ngrok với dev domain cố định → scripts/zalo_set_webhook.py gọi setWebhook(url, secret_token) → đọc kết quả verification hoặc gọi testWebhook.
- Lấy deeplink của bot trong Zalo Bot Creator → tạo mã QR dán ở kho và hiển thị trên dashboard.

Lưu ý: polling và webhook loại trừ nhau. Đã setWebhook thì getUpdates ngừng hoạt động mà không báo lỗi; muốn quay lại polling phải gọi deleteWebhook.

### 2. Kết nối nhân viên bằng mã mời

Webhook của Zalo Bot chỉ có from.id, display_name và chat.id, không có số điện thoại, nên không thể whitelist theo số như v1. Thay vào đó, mỗi nhân viên ghép tài khoản Zalo với hồ sơ của mình bằng mã mời:

- Admin thêm nhân viên trên dashboard (tên, vai trò staff/manager) → hệ thống sinh mã mời 6 ký tự, dùng 1 lần, hết hạn sau 24 giờ, kèm QR/deeplink của bot.
- Nhân viên quét QR hoặc bấm link → mở khung chat 1:1 với bot → gửi mã.
- Worker thấy chat_id chưa ghép → kiểm tra mã → lưu zalo_user_id, zalo_chat_id vào staff → bot chào bằng tên và gửi cú pháp.
- Mã sai/hết hạn → từ chối, không ghi gì. Sai quá 5 lần trong 15 phút → tạm khóa chat_id đó.

```text
Nhân viên: K7P2Q9
Bot:       Chào Lan 👋 Bạn đã được kết nối với kho quán Mộc.
           Cú pháp: Nhập/Xuất [số lượng] [đơn vị] [nguyên liệu] [giờ ngày]
           Ví dụ:   Nhập 50 kg bột mì 14h 28/10
```

### 3. Xử lý một tin nhắn (luồng chính)

![Hình 2. Flowchart: verify secret → lưu hàng đợi → worker → nhận diện → router → parser → validate → ghi hoặc hỏi xác nhận → trả lời.](assets/figure-2.png)

*Hình 2. Flowchart: verify secret → lưu hàng đợi → worker → nhận diện → router → parser → validate → ghi hoặc hỏi xác nhận → trả lời.*

- Zalo gửi POST /webhooks/zalo kèm header X-Bot-Api-Secret-Token.
- api so khớp secret bằng hmac.compare_digest; sai → 403, không lưu.
- Adapter chuẩn hóa thành InboundMessage{channel, message_id, sender_id, chat_id, display_name, event, text, sent_at} → INSERT ... ON CONFLICT (channel, message_id) DO NOTHING → trả 200 ngay.
- worker lấy tin bằng SELECT ... FOR UPDATE SKIP LOCKED, gửi sendChatAction(typing).
- Nhận diện người gửi theo chat_id. Chưa ghép → luồng mã mời.
- Sự kiện không phải text (ảnh, sticker, voice, unsupported) → bot trả lời hướng dẫn gõ bằng chữ.
- Router: lệnh hệ thống (OK, Sai, Hủy, Tồn ..., Hướng dẫn) → xử lý trực tiếp; tin bắt đầu bằng Nhập/Xuất hoặc parser nhận ra lệnh kho → nhánh kho; còn lại: manager → Q&A, staff → hướng dẫn cú pháp.
- Parser cascade: regex → NER (ngưỡng confidence) → LLM structured output (JSON schema, validate bằng Pydantic).
- Validate: nguyên liệu có trong danh mục (khớp cả tên gọi khác), đơn vị hợp lệ và quy đổi được, số lượng > 0, xuất không vượt tồn, thời gian không ở tương lai và không quá 7 ngày trước.
- Ghi: tin đọc bằng regex → ghi inventory_log ngay; tin đọc bằng NER/LLM → tạo pending_actions và hỏi lại.
- sendMessage trả lời; cập nhật trạng thái inbound_messages (done/failed kèm lỗi) và ghi outbound_messages.

### 4. Xác nhận, sửa và hủy

- **OK** → ghi bản chờ vào inventory_log; lưu mẫu vào training_samples với verified = true.
- **Sai** → hủy bản chờ, lưu mẫu kèm cờ sai để manager duyệt; bot nhắc gõ lại đúng cú pháp.
- Bản chờ không được trả lời trong 10 phút → tự hủy.
- **Hủy** → thêm bản ghi bù trừ (reverses_id) cho bản ghi gần nhất của chính người đó, chỉ trong 30 phút. Sau 30 phút, manager sửa trên dashboard (cũng bằng bản ghi bù trừ, không UPDATE/DELETE sổ cái).
- Bot API hiện chỉ gửi text, ảnh, sticker, voice (không có nút bấm), nên xác nhận bằng cách gõ OK/Sai.

```text
Nhân viên: vừa lấy 3 thùng sữa ra quầy
Bot:       Mình hiểu là: XUẤT 3 thùng sữa (= 72 hộp), lúc 9:05 hôm nay.
           Đúng thì trả lời OK, sai thì gõ Sai.
Nhân viên: ok
Bot:       ✅ Đã ghi. Tồn sữa: 48 hộp.
```

### 5. Hỏi đáp của manager

- Chỉ role manager được hỏi; staff hỏi thì bot trả lời hướng dẫn.
- LLM nhận câu hỏi + vài tool viết sẵn: get_stock(item), get_movements(item, from, to, action), top_items(period), staff_activity(period). Câu hỏi ngoài các tool → SQL agent (LangChain) làm fallback.
- Truy vấn chạy bằng role Postgres riêng, chỉ có quyền SELECT trên các view nghiệp vụ (không thấy admins, staff), statement_timeout 5 giây, tối đa 200 dòng.
- Câu trả lời tối đa 2.000 ký tự (giới hạn của sendMessage); dài hơn thì cắt thành nhiều tin hoặc gửi link dashboard.

### 6. Báo cáo định kỳ

- APScheduler chạy trong worker: 21:30 mỗi ngày và 07:00 ngày 1 mỗi tháng (giờ Asia/Ho_Chi_Minh), có misfire_grace_time và coalesce để laptop tắt lúc chạy vẫn bù lại được.
- Gửi sendMessage tới zalo_chat_id của các manager: nhập/xuất trong kỳ, tồn thấp hơn mức tối thiểu, nhân viên gõ sai nhiều; kèm link dashboard để xem chi tiết.
- Chưa chắc bot được chủ động nhắn khi manager lâu không tương tác — phải test ở Pha 0. Phương án dự phòng: manager gõ Báo cáo để nhận, hoặc xem trên dashboard.

### 7. Dashboard

- Đăng nhập bằng JWT; các trang: Login, Stock, Transactions, Staff (thêm/khóa, tạo mã mời, QR bot), Items (danh mục, tên gọi khác, quy đổi), Labels (duyệt nhãn), Chat (web chat demo), Reports.
- Web chat demo: POST /api/chat/messages → adapter web → cùng hàng đợi và worker như Zalo; trang chat đọc câu trả lời qua GET /api/chat/messages (polling 1–2 giây).

### 8. Data flywheel

- Mọi tin được nhân viên xác nhận OK và mọi chỉnh sửa của manager trên dashboard đi vào training_samples.
- Output của LLM chỉ thành nhãn train khi đã được người xác nhận — không lấy nguyên output LLM.
- Định kỳ (vd mỗi tuần) export BIO → retrain trên Colab → so F1 trên golden set → bản tốt hơn đẩy lên HF Hub → worker tải về khi khởi động lại.

## API sử dụng

### Zalo Bot API

Mọi method gọi dạng POST https://bot-api.zaloplatforms.com/bot{BOT_TOKEN}/{method}, body JSON. Token nằm ngay trong URL nên phải tắt log URL của HTTP client (httpx) và không in lỗi kèm URL.

| **Method** | **Tham số chính** | **Dùng ở đâu trong Storagemate** |
|---|---|---|
| getMe | — | Kiểm tra token lúc khởi động và trong /health |
| setWebhook | url (HTTPS public), secret_token (8–256 ký tự) | scripts/zalo_set_webhook.py; chạy lại khi đổi domain |
| deleteWebhook | — | Chuyển về polling khi dev |
| getWebhookInfo | — | Healthcheck, debug |
| testWebhook | — | Debug endpoint (có hạn mức mỗi ngày) |
| getUpdates | timeout (mặc định 30s) | Polling khi dev local; mỗi lần trả tối đa 1 update |
| sendMessage | chat_id, text (1–2.000 ký tự), parse_mode (tùy chọn) | Xác nhận, báo lỗi, hỏi đáp, báo cáo |
| sendChatAction | chat_id, action = typing | Hiện "đang soạn tin" khi chạy NER/LLM |
| sendPhoto | chat_id, photo (URL), caption | Tùy chọn: gửi ảnh biểu đồ trong báo cáo |
| sendSticker <br> sendVoice | — | Không dùng |

### Webhook Zalo gửi tới Storagemate

```http
POST /webhooks/zalo
X-Bot-Api-Secret-Token: <ZALO_WEBHOOK_SECRET>
Content-Type: application/json
```

```json
{
  "ok": true,
  "result": {
    "event_name": "message.text.received",
    "message": {
      "message_id": "82599fa32f56d00e8941",
      "date": 1761984000000,
      "from": { "id": "...", "display_name": "Lan", "is_bot": false },
      "chat": { "id": "...", "chat_type": "PRIVATE" },
      "text": "Nhập 50 kg bột mì 14h 28/10"
    }
  }
}
```

- Loại sự kiện: message.text.received, message.image.received, message.sticker.received, message.voice.received, message.unsupported.received.
- Endpoint phải trả 2xx nhanh; xử lý nặng để worker làm. Giữ nguyên payload gốc (jsonb) trong inbound_messages để debug.
- Không dựa vào display_name để định danh (người dùng tự đổi được); dùng from.id và chat.id.
- Đơn vị của date và tên trường ảnh cần xác nhận lại bằng payload thật ở Pha 0.

![Hình 3. Vòng đời một tin: webhook trả 200 ngay, worker xử lý nền rồi gọi sendChatAction và sendMessage.](assets/figure-3.png)

*Hình 3. Vòng đời một tin: webhook trả 200 ngay, worker xử lý nền rồi gọi sendChatAction và sendMessage.*

### Mã lỗi Zalo Bot API và cách xử lý

| **Mã** | **Ý nghĩa (theo bảng mã lỗi)** | **Xử lý** |
|---|---|---|
| 400 | Sai đường dẫn hoặc tên method | Lỗi code — log và báo động, không retry |
| 401 | Token hết hạn hoặc không hợp lệ | Dừng gửi, báo admin trên dashboard và log |
| 403 | Lỗi phía server Zalo | Retry có backoff, tối đa 3 lần |
| 404 | Yêu cầu không hợp lệ | Log, không retry |
| 408 | Hết thời gian chờ (thường gặp với getUpdates) | Polling: gọi lại ngay; gửi tin: retry |
| 429 | Vượt giới hạn gọi API | Retry với exponential backoff + jitter |

### API nội bộ (FastAPI)

Mọi route /api/* yêu cầu JWT của admin. Dashboard gọi qua ngrok nên phải gửi header ngrok-skip-browser-warning và CORS cho phép domain Vercel cùng header này.

| **Route** | **Ai gọi** | **Mô tả** |
|---|---|---|
| POST /webhooks/zalo | Zalo | Verify secret, lưu hàng đợi, trả 200 |
| GET /health | Compose, CI | Kiểm tra DB, hàng đợi, getMe |
| POST /api/auth/login | Dashboard | OAuth2 password flow → JWT |
| GET /api/stock | Dashboard | Tồn hiện tại (view current_stock) |
| GET /api/transactions | Dashboard | Lịch sử nhập/xuất, lọc theo nguyên liệu, nhân viên, ngày |
| POST /api/transactions/{id}/reverse | Dashboard | Tạo bản ghi bù trừ |
| GET/POST/PATCH /api/items | Dashboard | Danh mục, tên gọi khác, đơn vị quy đổi, mức tồn tối thiểu |
| GET/POST/PATCH /api/staff | Dashboard | Nhân viên, vai trò, khóa/mở |
| POST /api/staff/{id}/invite | Dashboard | Sinh mã mời + deeplink/QR của bot |
| GET /api/labels <br> PATCH /api/labels/{id} | Dashboard | Duyệt/sửa nhãn cho flywheel |
| GET /api/reports/daily <br> GET /api/reports/monthly | Dashboard | Báo cáo theo kỳ |
| POST /api/chat/messages <br> GET /api/chat/messages | Web chat | Gửi tin vào pipeline, đọc câu trả lời |

### Dịch vụ ngoài khác

- **LLM API** (Gemini hoặc self-host, chốt ở Pha 2): parser fallback bằng structured output, hỏi đáp bằng tool calling.
- **Hugging Face Hub:** lưu và tải các version model NER (file ONNX không commit vào repo).
- **ngrok:** URL HTTPS cố định cho webhook Zalo và cho dashboard gọi API.

## Mô hình dữ liệu (PostgreSQL)

Tồn kho tính real-time từ inventory_log (tồn = Σ nhập − Σ xuất), nên sổ cái là nguồn sự thật duy nhất và chỉ được thêm, không UPDATE/DELETE. Dùng view thường current_stock (không cần materialized view ở quy mô 1 cửa hàng). Số lượng dùng NUMERIC, thời gian dùng timestamptz; tách event_time (giờ ghi trong tin) khỏi received_at (giờ webhook đến).

| **Bảng** | **Cột chính** | **Mục đích** |
|---|---|---|
| admins | id, email, password_hash, created_at | Tài khoản đăng nhập dashboard (1 admin, tạo bằng script) |
| staff | id, name, role (staff/manager), zalo_user_id (unique), zalo_chat_id, active, linked_at | Danh tính nhân viên; chat_id chưa có ở đây chỉ được gửi mã mời |
| invite_codes | id, staff_id, code, expires_at, used_at, failed_attempts | Mã ghép tài khoản, dùng 1 lần |
| items | id, name, base_unit, aliases, min_stock | Danh mục nguyên liệu + tên gọi khác + mức tồn tối thiểu |
| units | id, item_id, unit_name, factor | Quy đổi đơn vị (vd 1 thùng = 24 hộp → factor = 24) |
| inbound_messages | id, channel, message_id, chat_id, sender_id, event_name, text, payload (jsonb), received_at, status, attempts, error | Hàng đợi + chống trùng, UNIQUE(channel, message_id) |
| pending_actions | id, staff_id, chat_id, parsed (jsonb), parser_source, confidence, expires_at, status | Tin chờ nhân viên trả lời OK/Sai |
| inventory_log | id, item_id, action (IN/OUT), qty, unit, qty_base, event_time, received_at, staff_id, inbound_id, raw_message, parser_source, confidence, reverses_id | Sổ cái; Hủy/sửa = thêm bản ghi bù trừ |
| outbound_messages | id, chat_id, text, sent_at, zalo_message_id, status, error | Log tin bot gửi, để debug và đo độ trễ |
| training_samples | id, raw_message, labels (BIO/JSON), parser_source, verified, corrected_by, created_at | Mẫu để retrain NER (data flywheel) |

```sql
CREATE VIEW current_stock AS
SELECT i.id AS item_id, i.name, i.base_unit,
       COALESCE(SUM(CASE WHEN l.action = 'IN'
                         THEN l.qty_base ELSE -l.qty_base END), 0) AS qty
FROM items i
LEFT JOIN inventory_log l ON l.item_id = i.id
GROUP BY i.id, i.name, i.base_unit;
-- bản ghi bù trừ đảo action của bản gốc, nên tổng vẫn đúng
```

Ghi chú: multi-tenant để mở — thêm bảng stores và cột store_id khi cần, chưa làm ở pha đầu.

## Cú pháp tin nhắn & Hybrid parser

Nhân viên ghi theo cú pháp quy ước để dễ khoanh vùng dữ liệu: Nhập|Xuất [số lượng] [đơn vị] [nguyên liệu] [giờ] [ngày], ví dụ Nhập 50 kg bột mì 14h 28/10 hoặc Xuất 3 thùng sữa 9h 28/10. Thiếu giờ/ngày thì lấy thời điểm nhận tin.

| **Lệnh** | **Ai dùng** | **Kết quả** |
|---|---|---|
| Nhập ..., Xuất ... | staff, manager | Ghi sổ (hoặc hỏi xác nhận nếu đọc bằng NER/LLM) |
| OK, Sai | staff, manager | Xác nhận hoặc bỏ bản chờ |
| Hủy | staff, manager | Bù trừ bản ghi gần nhất của chính mình (trong 30 phút) |
| Tồn [nguyên liệu] | staff, manager | Xem nhanh tồn một nguyên liệu |
| Hướng dẫn | mọi người đã ghép | Gửi lại cú pháp và ví dụ |
| Báo cáo | manager | Nhận báo cáo ngày hiện tại |
| Câu hỏi tự do | manager | Hỏi đáp dữ liệu (Q&A) |

Parser chạy theo bậc thang (dừng ở bậc nào parse được thì thôi):

- **Regex** khớp đúng cú pháp (chấp nhận không dấu, viết tắt đơn vị) → nhanh, chính xác, không tốn model.
- Regex fail → **NER (ViDeBERTa/PhoBERT, ONNX)** trích entity từ câu tự nhiên hơn.
- NER confidence thấp → **LLM fallback** trả JSON theo schema cố định, validate bằng Pydantic.
- Vẫn không được → bot báo không hiểu và gửi ví dụ đúng cú pháp.

Sau khi parse, **validate** trước khi ghi: nguyên liệu có trong danh mục (khớp cả tên gọi khác), đơn vị hợp lệ và quy đổi được, số lượng > 0, xuất không làm tồn âm, thời gian hợp lý. Không hợp lệ → báo lỗi cụ thể, ví dụ:

```text
Nhân viên: Xuất 10 kg đường
Bot:       ⚠️ Tồn đường chỉ còn 6 kg, không thể xuất 10 kg. Kiểm tra lại số lượng nhé.
```

**Định vị:** cú pháp bắt buộc + regex là đường xử lý chính cho production (chính xác, không tốn model). NER và LLM đứng sau như lớp học tập và bắt lỗi mềm khi nhân viên gõ hơi sai cú pháp — và luôn có bước người xác nhận.

## Model NER + Data Flywheel

Train một model NER token-classification để trích các nhãn: ACTION (nhập/xuất), QUANTITY, UNIT, ITEM, TIME, DATE. Base model là ViDeBERTa-xsmall, so với PhoBERT-base làm mốc; dữ liệu train ban đầu là **synthetic** (template + random số lượng/nguyên liệu/thời gian), học format BIO từ PhoNER.

Vòng học lại an toàn (human-in-the-loop), **không** cập nhật trọng số realtime từng tin:

- Log mọi tin nhắn + kết quả parse + phản hồi OK/Sai của nhân viên vào training_samples.
- Khi regex fail, output của NER/LLM chỉ thành nhãn train sau khi nhân viên trả lời OK.
- Manager duyệt/sửa nhãn trên dashboard → dữ liệu sạch dần.
- Định kỳ (vd mỗi tuần) retrain NER trên Colab với dữ liệu mới.
- So sánh F1 trên golden set giữa các version → giữ bản tốt nhất, đẩy lên Hugging Face Hub.

Lý do không học realtime: một nhân viên gõ sai là có thể làm hỏng model; duyệt theo mẻ an toàn hơn nhiều.

Về mặt kỹ thuật, NER không bắt buộc cho production vì đã có cú pháp cứng + LLM; ở dự án này NER giữ vai trò học tập (đi hết vòng train → deploy → flywheel) và giảm số lần phải gọi LLM.

## Dữ liệu cần chuẩn bị

| **Dữ liệu** | **Dùng cho** | **Khi nào** | **Quy mô / ghi chú** |
|---|---|---|---|
| Danh mục nguyên liệu + tên gọi khác + quy đổi đơn vị | Validate, regex, seed DB | Pha 1 | 30–50 nguyên liệu của một quán; alias gồm cả không dấu, viết tắt |
| Golden set: tin thật có nhãn | Đo regex/LLM/NER sau mỗi thay đổi | Pha 1 | 100–200 tin do 5–10 người thật gõ; trộn đúng cú pháp, không dấu, nói tự nhiên, tin rác |
| Câu hỏi mẫu + đáp án | Đo Q&A agent | Pha 3 | 20–30 câu, đáp án tính từ dữ liệu giả lập |
| Synthetic BIO | Train NER | Pha 2 | 1.000–3.000 câu sinh từ template + danh mục |
| Mẫu flywheel | Retrain | Sau khi chạy | Tin đã được OK hoặc manager sửa |

Golden set phải là tin của người thật và tách hoàn toàn khỏi dữ liệu train; nếu test bằng synthetic, điểm sẽ đẹp giả tạo vì model chỉ học thuộc template. Một mẫu có nhãn:

```json
{"text": "nhap 3 thung sua 9h",
 "label": {"action": "IN", "qty": 3, "unit": "thùng", "item": "sữa tươi",
           "time": "09:00", "date": null}}
```

## Model & Dataset gợi ý

Không có dataset "nhập/xuất kho F&B" sẵn — bạn sẽ tự sinh synthetic cho domain hẹp này, dùng PhoNER chỉ để học format BIO.

**Model NER (HuggingFace) — ưu tiên fine-tune:**

| **Model** | **Dùng cho** | **Link** |
|---|---|---|
| Fsoft-AIC (ViDeBERTa) | ViDeBERTa-xsmall: lựa chọn chính, nhỏ, dễ nén ONNX | huggingface.co |
| vinai/phobert-base | Mốc so sánh; cần tách từ trước bằng VnCoreNLP | huggingface.co |
| vinai/phobert-large | Mạnh hơn nhưng nặng hơn | huggingface.co |
| FacebookAI/xlm-roberta-base | Đa ngữ, backup | huggingface.co |
| spaCy (blank vi) | NER đơn giản để học trước, không cần GPU | spacy.io |

**Dataset để học format / khởi động:**

| **Dataset** | **Nội dung** | **Link** |
|---|---|---|
| VinAIResearch/PhoNER_COVID19 | NER tiếng Việt chuẩn, định dạng BIO — học format từ đây | github.com |
| SEACrowd/pho_ner_covid | Bản đóng gói sẵn của PhoNER trên HF | huggingface.co |
| VLSP 2016/2018 NER | NER generic (người/tổ chức/địa điểm) | tra "VLSP NER" |
| Synthetic tự sinh | Template nhập/xuất + random — nguồn chính cho domain | tự tạo |

## Tech stack

Chọn tối giản, Python-first cho phần AI, React + Vite cho dashboard (SPA, FastAPI là API duy nhất), dễ tách service để scale sau.

| **Lớp** | **Chọn** | **Docs** |
|---|---|---|
| Kênh nhắn | Zalo Bot Platform (1:1) + web chat demo | docs.zaloplatforms.com/docs/BOT |
| Backend | FastAPI (Python): api + worker | fastapi.tiangolo.com |
| Hàng đợi | Bảng Postgres + FOR UPDATE SKIP LOCKED | postgresql.org/docs |
| Database | PostgreSQL 16 | postgresql.org/docs |
| ORM | SQLAlchemy 2.0 + Alembic | docs.sqlalchemy.org |
| Q&A agent | LLM tool calling + LangChain SQL agent (fallback) | docs.langchain.com |
| Train NER | HuggingFace Transformers + Colab | huggingface.co/docs/transformers |
| LLM API | Chốt ở Pha 2 (Gemini hoặc self-host) | chốt sau |
| Dashboard | React + Vite (SPA) | vite.dev/guide |
| Auth | FastAPI OAuth2 + JWT, tự build | fastapi.tiangolo.com/tutorial/security |
| Host web | Vercel | vite.dev/guide/static-deploy |
| Host api + worker + DB | Laptop Windows · Docker Desktop (WSL 2) | docs.docker.com/desktop/features/wsl |
| Tunnel | ngrok (dev domain free, URL cố định) | ngrok.com/docs |
| CI/CD | GitHub Actions + self-hosted runner | docs.github.com/actions |

Hướng scale: tách worker thành nhiều tiến trình (scheduler riêng) khi tải lớn; tách NER thành service riêng; thêm store_id cho multi-tenant; chuyển sang Zalo OA bằng adapter mới nếu cần thương hiệu doanh nghiệp.

## Roadmap theo pha

Mỗi pha chạy được end-to-end trước khi thêm độ thông minh — xây tăng dần, không ôm hết một lượt.

| **Pha** | **Mục tiêu** | **Deliverable** | **Ước tính** |
|---|---|---|---|
| 0 | Dựng Zalo Bot | Tạo bot, getMe, bot echo qua polling; chuyển sang webhook qua ngrok + verify secret; lưu payload thật; test gửi tin chủ động sau vài ngày im lặng | ~3–5 ngày |
| 1 | Ingestion không-AI chạy thật | Adapter Zalo + web chat, hàng đợi + chống trùng, mã mời, regex parser, validate, sổ cái + Hủy, báo cáo ngày/tháng; danh mục nguyên liệu + golden set | ~2 tuần |
| 2 | Train NER + LLM fallback | Synthetic BIO, ViDeBERTa-xsmall (so với PhoBERT-base) trên Colab, nén ONNX int8, cascade regex → NER → LLM + xác nhận OK/Sai | ~2–3 tuần |
| 3 | Q&A + dashboard | Tool calling + SQL agent fallback, dashboard React + Vite, label review UI, trang Staff/mã mời | ~2–3 tuần |
| Cổng | Test local end-to-end | Toàn bộ luồng chạy trên Docker Compose; chạy golden set và bộ câu hỏi Q&A — xong mới qua Pha 4 | — |
| 4 | Auth & phân quyền | Login JWT, 1 admin, role manager, khóa mã mời khi sai nhiều lần | ~1 tuần |
| 5 | Deploy | Vercel + Docker Desktop (WSL 2) + ngrok + GitHub Actions | ~1 tuần |
| 6 | Flywheel + mở rộng | Retrain định kỳ; (tùy chọn) OCR ảnh hóa đơn; multi-tenant | liên tục |

Nếu thời gian hackathon ngắn: demo Pha 0–1 (Zalo Bot + regex + sổ cái + báo cáo) cộng LLM fallback và Q&A đơn giản; NER và flywheel trình bày như hướng phát triển.

## Auth & phân quyền (Pha 4)

Hai lớp xác thực khác nhau: bot nhận diện bằng tài khoản Zalo đã ghép qua mã mời, dashboard đăng nhập bằng mật khẩu + JWT. Secret webhook và mã mời làm ngay từ Pha 0–1; Pha 4 hoàn thiện phần dashboard trước khi deploy.

| **Ai** | **Kênh** | **Xác thực** | **Được làm gì** |
|---|---|---|---|
| Admin (chủ quán) | Dashboard | email + mật khẩu → JWT | Quản lý nhân viên/mã mời, xem tồn, sửa giao dịch, duyệt nhãn |
| Manager | Zalo Bot | chat_id đã ghép, role = manager | Nhập/xuất + hỏi đáp + nhận báo cáo |
| Nhân viên | Zalo Bot | chat_id đã ghép, role = staff | Nhập/xuất, xem tồn nhanh, Hủy |
| Người lạ | Zalo Bot | chat_id chưa ghép | Chỉ được gửi mã mời; sai mã → từ chối, không ghi gì |

- **Danh tính trên Zalo = from.id / chat.id trong webhook**, ghép với staff qua mã mời. Không dùng display_name.
- **Deeplink/QR chỉ để mở khung chat**, không cấp quyền; mã mời mới là thứ chặn người lạ ghi dữ liệu giả.
- **Webhook:** so X-Bot-Api-Secret-Token bằng hmac.compare_digest; secret ngẫu nhiên ≥ 32 ký tự; token và secret chỉ nằm trong .env.
- **Không lộ token:** tắt log request URL của httpx, không đưa URL vào thông báo lỗi.
- **Dashboard:** tự build theo tutorial chính thức OAuth2 password flow + JWT, ký token bằng PyJWT, băm mật khẩu bằng pwdlib (FastAPI security).
- **1 admin**, tạo bằng scripts/create_admin.py; chưa có trang đăng ký.

## Deploy (Pha 5)

Web lên Vercel; api, worker và PostgreSQL chạy Docker Compose trên laptop Windows (Docker Desktop + WSL 2), ra internet qua một URL ngrok cố định. Server chỉ bật khi test/demo nên chi phí hosting là $0.

![Hình 4. Topology deploy: mọi traffic từ ngoài vào laptop đi qua ngrok tới api; worker là nơi gọi Zalo Bot API và LLM.](assets/figure-4.png)

*Hình 4. Topology deploy: mọi traffic từ ngoài vào laptop đi qua ngrok tới api; worker là nơi gọi Zalo Bot API và LLM.*

Luồng CI/CD khi push code:

- Mở PR → GitHub Actions chạy lint + test (gồm test parser trên golden set) trên runner của GitHub.
- Merge main → Vercel tự build apps/web (Root Directory = apps/web).
- Merge main → self-hosted runner trên laptop chạy docker compose up -d --build — chỉ chạy khi máy đang bật. Repo để private, và workflow deploy chỉ chạy theo push lên main, không bao giờ theo pull_request.
- ngrok trỏ dev domain cố định vào container api; URL này dùng cho webhook Zalo và cho web gọi API. Gói free chèn trang cảnh báo trước traffic trình duyệt, nên dashboard phải gửi header ngrok-skip-browser-warning; giới hạn 20.000 request và 1 GB/tháng.
- Sau mỗi lần đổi domain: chạy lại scripts/zalo_set_webhook.py.

Vì sao không dùng cloud free: Render free chỉ có 512 MB RAM, ngủ sau 15 phút, Postgres free hết hạn sau 30 ngày (Render free); Hugging Face giờ yêu cầu gói trả phí cho Docker Space (HF Spaces). OrbStack chỉ chạy trên macOS, nên trên Windows dùng Docker Desktop + WSL 2 (Docker WSL 2).

## Cấu trúc project

Một monorepo trên GitHub: Vercel chỉ build apps/web; Docker Compose chạy api + worker + postgres trên laptop; ml/ là nơi train, chạy trên Colab và không deploy.

```text
storagemate/
├── apps/
│   ├── api/                        # 1 codebase, 2 process: api + worker
│   │   ├── app/
│   │   │   ├── main.py             # FastAPI: webhook + REST
│   │   │   ├── worker.py           # vòng lặp đọc hàng đợi + APScheduler
│   │   │   ├── core/               # config.py, security.py (JWT, verify secret Zalo)
│   │   │   ├── db/                 # session.py, models.py (SQLAlchemy)
│   │   │   ├── routers/            # webhooks.py, auth.py, stock.py, transactions.py,
│   │   │   │                       # items.py, staff.py, labels.py, reports.py, chat.py
│   │   │   ├── channels/           # base.py (InboundMessage, ChannelAdapter), zalo.py, web.py
│   │   │   ├── services/
│   │   │   │   ├── zalo_client.py  # gọi Bot API bằng HTTPX, ẩn token khỏi log
│   │   │   │   ├── router.py       # phân loại tin
│   │   │   │   ├── onboarding.py   # mã mời
│   │   │   │   ├── parser/         # regex.py, ner.py (ONNX), llm.py, validate.py
│   │   │   │   ├── ledger.py       # ghi sổ, bù trừ, quy đổi đơn vị
│   │   │   │   ├── confirm.py      # pending OK/Sai, Hủy
│   │   │   │   ├── qa/             # tools.py, agent.py
│   │   │   │   └── reports.py      # báo cáo ngày/tháng
│   │   │   └── jobs/               # lịch APScheduler
│   │   ├── alembic/                # migrations
│   │   ├── tests/                  # golden set, test webhook, test parser
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   └── web/                        # React + Vite: dashboard
│       ├── src/
│       │   ├── pages/              # Login, Stock, Transactions, Staff, Items,
│       │   │                       # LabelReview, Chat, Reports
│       │   ├── components/
│       │   ├── api/                # client gọi FastAPI (TanStack Query)
│       │   └── auth/               # lưu token, route cần đăng nhập
│       ├── vite.config.ts
│       └── package.json
├── ml/                             # train: chạy trên Colab, không deploy
│   ├── notebooks/                  # train_ner.ipynb
│   ├── data/                       # synthetic BIO, golden/ (gitignore dữ liệu thật)
│   └── scripts/                    # generate_synthetic.py, export_onnx.py, evaluate.py
├── models/                         # file .onnx — không commit, tải từ HF Hub
├── scripts/                        # create_admin.py, seed_items.py,
│                                   # zalo_poll.py, zalo_set_webhook.py
├── .github/workflows/              # ci.yml (test PR), deploy-api.yml (self-hosted runner)
├── docker-compose.yml              # api + worker + postgres
├── .env.example                    # không commit .env
└── README.md
```

Biến môi trường chính (.env.example):

```dotenv
ZALO_BOT_TOKEN=123456789:xxxxxxxx
ZALO_WEBHOOK_SECRET=<chuỗi ngẫu nhiên ≥ 32 ký tự>
PUBLIC_BASE_URL=https://<ten-ban>.ngrok-free.app
DATABASE_URL=postgresql+psycopg://storagemate:***@postgres:5432/storagemate
DATABASE_URL_READONLY=postgresql+psycopg://qa_reader:***@postgres:5432/storagemate
JWT_SECRET=<chuỗi ngẫu nhiên>
LLM_API_KEY=...
HF_MODEL_REPO=<user>/storagemate-ner
TZ=Asia/Ho_Chi_Minh
CORS_ORIGINS=https://<app>.vercel.app
```

## Tài liệu cần đọc

Đọc theo thứ tự ưu tiên, bám theo pha — mỗi mục đủ để hoàn thành pha tương ứng.

- **Zalo Bot** — tổng quan, tạo bot, webhook, API reference (Pha 0): docs.zaloplatforms.com/docs/BOT
- **FastAPI** — First Steps + Request Body + Background tasks (Pha 0–1): fastapi.tiangolo.com/tutorial
- **PostgreSQL + SQLAlchemy** — ORM quickstart, SKIP LOCKED (Pha 1): docs.sqlalchemy.org/en/20/orm/quickstart.html
- **HuggingFace token classification** — tutorial NER (Pha 2): huggingface.co/docs/transformers/tasks/token_classification
- **LangChain SQL agent** — cho phần fallback của Q&A (Pha 3): docs.langchain.com/oss/python/langchain/sql-agent

### Stack đã chốt

Một ngôn ngữ cho backend + ML (Python); dashboard React + Vite chỉ gọi API của FastAPI, không chạm DB trực tiếp — nên chỉ dùng một ORM (SQLAlchemy). Lưu ý: chỉ PhoBERT cần tách từ trước bằng VnCoreNLP (chạy Java, làm image nặng thêm); với ViDeBERTa xem model card để dùng đúng tokenizer.

| **Pha** | **Lớp** | **Chốt dùng** | **Vai trò** | **Docs** |
|---|---|---|---|---|
| 0 | Ngôn ngữ backend | Python 3.12 | backend + ML | docs.python.org |
| 0 | Môi trường & package | uv | venv + cài thư viện | docs.astral.sh/uv |
| 0 | Web framework | FastAPI | webhook + REST API | fastapi.tiangolo.com |
| 0 | Validation | Pydantic v2 | schema request/response, output LLM | docs.pydantic.dev |
| 0 | Server | Uvicorn | chạy FastAPI | uvicorn.org |
| 0 | HTTP client | HTTPX | gọi Zalo Bot API | python-httpx.org |
| 0 | Kênh nhắn | Zalo Bot Platform | nhận/gửi tin 1:1 | docs.zaloplatforms.com |
| 0 | Tunnel | ngrok (dev domain free) | URL cố định cho webhook | ngrok.com/docs |
| 0 | Chạy container | Docker Desktop (WSL 2) | chạy Compose trên Windows | docs.docker.com |
| 1 | Database | PostgreSQL 16 | sổ cái, hàng đợi, mẫu train | postgresql.org/docs |
| 1 | ORM | SQLAlchemy 2.0 | truy cập DB từ Python | docs.sqlalchemy.org |
| 1 | Migration | Alembic | quản lý thay đổi schema | alembic.sqlalchemy.org |
| 1 | Parser | Python re | regex cú pháp Nhập/Xuất | docs.python.org/3/library/re |
| 1 | Lịch chạy | APScheduler | báo cáo ngày/tháng (trong worker) | apscheduler.readthedocs.io |
| 1 | Chạy local | Docker Compose | api + worker + postgres một lệnh | docs.docker.com/compose |
| 2 | Base model NER | ViDeBERTa-xsmall (so với PhoBERT-base) | nhỏ, dễ nén | huggingface.co/Fsoft-AIC |
| 2 | Train NER | HF Transformers | fine-tune token classification | huggingface.co/docs/transformers |
| 2 | Dữ liệu train | HF Datasets | load + format BIO | huggingface.co/docs/datasets |
| 2 | Deep learning | PyTorch | backend của Transformers | pytorch.org/docs |
| 2 | Đánh giá NER | seqeval | F1 theo entity | github.com/chakki-works/seqeval |
| 2 | Nén model | Optimum (ONNX) + ONNX Runtime | export + quantize int8, chạy trong worker | huggingface.co/docs/optimum |
| 2 | Môi trường train | Google Colab | GPU miễn phí | Colab FAQ |
| 2 | Lưu model | Hugging Face Hub | version NER | huggingface.co/docs/hub |
| 2 | LLM fallback | chốt ở Pha 2 (Gemini hoặc self-host) | parse khi regex + NER fail | chốt sau |
| 3 | Q&A agent | LLM tool calling + LangChain (fallback) | câu hỏi → tool/SQL chỉ đọc | docs.langchain.com |
| 3 | Ngôn ngữ frontend | TypeScript | dashboard | typescriptlang.org/docs |
| 3 | UI library | React | component + state | react.dev/learn |
| 3 | Build tool | Vite | dev server + build SPA | vite.dev/guide |
| 3 | Routing | React Router | các trang Login, Stock, Staff... | reactrouter.com |
| 3 | Gọi API | TanStack Query | fetch + cache dữ liệu từ FastAPI | tanstack.com/query |
| 3 | UI | Tailwind CSS + shadcn/ui | giao diện | ui.shadcn.com |
| 3 | Biểu đồ | Recharts | chart tồn kho | recharts.org |
| 4 | Login dashboard | FastAPI OAuth2 + JWT | đăng nhập admin | fastapi.tiangolo.com |
| 4 | Ký token | PyJWT | tạo + verify JWT | pyjwt.readthedocs.io |
| 4 | Băm mật khẩu | pwdlib | hash password admin | github.com/frankie567/pwdlib |
| 4 | CORS | FastAPI CORSMiddleware | cho web trên Vercel gọi API | fastapi.tiangolo.com/tutorial/cors |
| 5 | Host web | Vercel | build apps/web khi merge main | vite.dev/guide/static-deploy |
| 5 | Monorepo trên Vercel | Root Directory | chỉ build thư mục web | vercel.com/docs/monorepos |
| 5 | CI | GitHub Actions | lint + test mỗi PR | docs.github.com/actions |
| 5 | CD về laptop | GitHub self-hosted runner | docker compose up khi merge main | docs.github.com |

### Lộ trình đọc cho kênh, web, auth, deploy

Đọc đúng trang, đúng thứ tự — mỗi bước đủ để làm phần tương ứng, không cần đọc hết docs.

| **Bước** | **Đọc trang** | **Nắm được** | **Pha** |
|---|---|---|---|
| 1 | Zalo Bot — tổng quan, tạo bot, API reference | token, getMe, sendMessage, getUpdates | 0 |
| 2 | Zalo Bot — webhook | setWebhook, secret token, payload, testWebhook | 0 |
| 3 | Zalo Bot — nhóm chat (đang thử nghiệm) | vì sao chưa dùng nhóm | 0 |
| 4 | React — Learn: Thinking in React, Managing State | chia component, state, props | 3 |
| 5 | Vite — Getting Started + Env Variables | tạo project, biến VITE_API_URL | 3 |
| 6 | React Router — tutorial | route, trang cần đăng nhập | 3 |
| 7 | TanStack Query — Quick Start | gọi API FastAPI, loading, cache | 3 |
| 8 | FastAPI — OAuth2 + JWT | login, hash mật khẩu, verify token | 4 |
| 9 | FastAPI — CORS | cho domain Vercel gọi API | 4 |
| 10 | Docker Desktop WSL 2 + Compose | chạy api + worker + postgres trên Windows | 5 |
| 11 | ngrok — Getting Started + giới hạn free | dev domain cố định, trang cảnh báo, giới hạn request | 5 |
| 12 | Vite — Deploy to Vercel + Vercel monorepos | deploy web từ apps/web | 5 |
| 13 | GitHub Actions — Quickstart + self-hosted runners | CI cho PR, CD về laptop | 5 |

## Rủi ro & quyết định còn mở

**Rủi ro:**

- **Zalo Bot Creator đang beta:** tối đa 3 bot/tài khoản (dùng 1 bot dev, 1 bot demo); Zalo có thể đổi luật bất cứ lúc nào → giữ channel adapter để chuyển sang Zalo OA khi cần.
- **Gửi tin chủ động chưa được xác nhận:** tài liệu không nói bot có nhắn được cho người lâu không tương tác hay không → test ở Pha 0; dự phòng bằng lệnh Báo cáo và dashboard.
- **Không có nút bấm qua Bot API:** xác nhận bằng text OK/Sai.
- **Payload không có số điện thoại:** dùng mã mời để ghép tài khoản.
- **Polling và webhook loại trừ nhau; getUpdates trả 1 update/lần:** polling chỉ dùng khi dev.
- **Chưa rõ Zalo có gửi lại webhook khi server lỗi không:** laptop tắt thì tin gửi lúc đó có thể mất → kiểm tra ở Pha 0, ghi rõ trong demo.
- **Cold start NER:** pha đầu gần như không có dữ liệu thật, phụ thuộc synthetic; cần template đủ đa dạng.
- **Laptop tắt = bot offline:** đã chấp nhận vì server chỉ bật khi test/demo.
- **ngrok free:** 20.000 request và 1 GB/tháng; trang cảnh báo trước traffic trình duyệt.
- **Self-hosted runner:** chỉ an toàn với repo private hoặc workflow chỉ chạy khi push lên main.

**Đã chốt:**

- **Kênh:** Zalo Bot 1:1 + web chat demo qua channel adapter; không dùng nhóm, không dùng Zalo OA ở pha đầu.
- **Định danh:** ghép tài khoản Zalo bằng mã mời; chỉ manager được hỏi đáp dữ liệu.
- **Ingestion:** webhook trả 200 ngay; hàng đợi Postgres + chống trùng; 3 container api, worker, postgres.
- **Sổ cái chỉ thêm:** sửa/hủy bằng bản ghi bù trừ; tồn real-time qua view current_stock.
- **Xác nhận:** tin đọc bằng NER/LLM phải được OK trước khi ghi.
- **1 cửa hàng trước:** schema chừa chỗ thêm store_id.
- **Có quy đổi đơn vị:** bảng units + factor; qty_base lưu theo đơn vị gốc.
- **Cú pháp bắt buộc:** regex là đường chính; NER/LLM là lớp học + bắt lỗi khi gõ hơi sai.
- **Kênh manager:** Zalo (hỏi nhanh, nhận báo cáo) + dashboard (xem sâu, duyệt nhãn).
- **Stack:** FastAPI + PostgreSQL + SQLAlchemy; frontend React + Vite; NER ViDeBERTa-xsmall + ONNX int8.
- **Deploy:** web lên Vercel; api + worker + DB chạy Docker Desktop (WSL 2) trên laptop, ra internet qua ngrok; CI/CD bằng GitHub Actions + self-hosted runner.

**Còn mở:**

- Chọn LLM: Gemini free tier hay self-host (Vistral/PhoGPT) — chốt ở Pha 2.
- Bot có gửi tin chủ động được không, và Zalo có retry webhook không — kết luận sau Pha 0.
- Có cần tách NER thành service riêng không — quyết định khi đo được bộ nhớ/độ trễ của worker.

## Nguồn tham khảo

- Zalo Bot — tài liệu chính thức
- Zalo Bot — tương tác với nhóm chat (đang thử nghiệm nội bộ)
- Hướng dẫn tạo bot Zalo cá nhân bằng Zalo Bot Creator (Tino, 10/2026)
- Tổng hợp API Zalo Bot: setWebhook, payload, mã lỗi (goclaw issue #1542)
- Zalo OA: gói dịch vụ và chi phí (Viettel Store)
- WhatsApp pricing change từ 1/10/2026 (respond.io)
- ngrok — giới hạn gói free
- GitHub — bảo mật self-hosted runner
