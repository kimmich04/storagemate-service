# Integrations
> last-updated: 2026-11-06

External services and tools. Env var NAMES only — never values. Names match `app/config.py` + `.env.example`.

## External services
| Service | Used for | Auth (env var) | Failure mode |
|---------|----------|----------------|--------------|
| Zalo Bot Platform (beta) | 1:1 chat in/out | `ZALO_BOT_TOKEN`, `ZALO_WEBHOOK_SECRET` | Beta rules may change; max 3 bots/account (1 dev, 1 demo); error table in api-contracts.md |
| LLM (Gemini Flash-Lite, tentative) | Parser fallback (structured output), Q&A tool calling | `GEMINI_API_KEY`, `LLM_MODEL` | Down/limited → parser reports "not understood"; Q&A unavailable. Final choice Phase 2 |
| Hugging Face Hub | NER `.onnx` versions | `HF_MODEL_REPO` (+ `NER_MODEL_PATH` local) | Missing model → cascade skips NER (regex → LLM) |
| ngrok (free dev domain) | Fixed HTTPS URL for webhook + dashboard API | `PUBLIC_BASE_URL` | 20k req + 1 GB/month; browser warning page; laptop off = bot offline |
| Vercel | Hosts the dashboard (separate repo) | `CORS_ORIGINS` here | — |
| PostgreSQL 16 | Data + queue | `DATABASE_URL`, `DATABASE_URL_READONLY` | — |

Other config: `JWT_SECRET`, `JWT_EXPIRE_MINUTES`, `TZ=Asia/Ho_Chi_Minh`.

## Webhooks / callbacks
- Inbound: `POST /webhooks/zalo`, verified by `X-Bot-Api-Secret-Token`. Return 2xx fast; only enqueue
  into `inbound_messages`; the worker answers (data-flow §3a).
- Dedup on `(channel, external_id)` via `INSERT … ON CONFLICT DO NOTHING` (`app/messaging/inbox.py`).
- **Zalo does NOT retry**: messages sent while the server is down are lost (verified 2026-11-04).
- Human walkthrough (Vietnamese, file/function level): `docs/zalo-webhook-flow.md`.

## Phase 0 findings (verified live 2026-11-04 unless marked)
| Question | Answer |
|----------|--------|
| Can the bot message a user after days of silence? | <!-- unknown: not tested yet --> |
| Does Zalo retry failed webhooks? | **No.** Server off → ngrok returned 502 to Zalo once per message; after restart, nothing redelivered (watched several minutes). |
| Unit of `message.date` | **Milliseconds** since epoch. |
| Webhook body shape | `{event_name, message}` — no `{ok, result}` wrapper. `getUpdates` returns `{ok, result: <one event>}`. |
| setWebhook verification | Zalo POSTs `{event_name: "webhook.test", message: {date, message_id, text}}` (no `chat`/`from`) with the secret header; returns `verification.outcome` = `webhook.ok` or `webhook.http.<status>` (e.g. `webhook.http.404` = wrong/offline ngrok domain). |
| No webhook set | `getWebhookInfo` → 404, `deleteWebhook` → 400 (not an empty url). Scripts treat these as "no webhook". |
| Text event fields | `message_id`, `date`, `message_type: CHAT_TEXT`, `from{id, display_name, is_bot}`, `chat{id, chat_type: PRIVATE}`, `text`. In 1:1 chat `chat.id == from.id`. |
| Image event field names | <!-- unverified: adapter assumes `photo_url` + `caption`; send a photo and check data/zalo_samples --> |

Dev-machine note: Windows `curl.exe` to `*.ngrok-free.dev` may fail (`CRYPT_E_REVOCATION_OFFLINE`, connection reset) due to
ISP/antivirus — unrelated to Zalo. Check via `localhost` + ngrok inspector `http://127.0.0.1:4040`.

## MCP servers used in dev
| MCP | Why this project needs it |
|-----|---------------------------|
| github | Issues/PRs, CI status |
| context7 | Version-correct docs: FastAPI, SQLAlchemy 2.0, Pydantic v2, APScheduler 3.x, LangChain, Transformers/Optimum |
| mermaid | Diagrams in system-design/*.md |
