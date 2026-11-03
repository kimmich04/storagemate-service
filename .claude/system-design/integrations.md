# Integrations
> last-updated: 2026-11-02

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
- Inbound: `POST /webhooks/zalo`, verified by `X-Bot-Api-Secret-Token`. Return 2xx fast; only enqueue.
- Dedup on `(channel, message_id)` — safe if Zalo redelivers.
- <!-- unknown: does Zalo retry when we're down? Phase 0 test. If not, messages sent while the laptop is off are lost. -->

## Phase 0 open questions (record answers here)
| Question | Answer |
|----------|--------|
| Can the bot message a user after days of silence? | <!-- unknown --> |
| Does Zalo retry failed webhooks? | <!-- unknown --> |
| Unit of `message.date` (ms?) | <!-- unknown --> |
| Image event field names | <!-- unknown --> |

## MCP servers used in dev
| MCP | Why this project needs it |
|-----|---------------------------|
| github | Issues/PRs, CI status |
| context7 | Version-correct docs: FastAPI, SQLAlchemy 2.0, Pydantic v2, APScheduler 3.x, LangChain, Transformers/Optimum |
| mermaid | Diagrams in system-design/*.md |
