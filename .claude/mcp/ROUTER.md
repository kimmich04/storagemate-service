# MCP ROUTER — storagemate-service

Pick MCP by task. API keys live in your **global** ~/.claude env, never in this repo.

| When the task is... | Reach for | Why |
|---------------------|-----------|-----|
| Library/API docs (FastAPI, SQLAlchemy, Pydantic, APScheduler, LangChain, HF) | **context7** | Version-correct docs; required before codegen (global rule) |
| Issues, PRs, CI status | **github** | |
| ERD / sequence / container diagram | **mermaid** | Diagrams live as text in `system-design/*.md` |
| Zalo Bot docs (`docs.zaloplatforms.com/docs/BOT`), ngrok/Vercel docs | built-in browser / web-fetch | No MCP for Zalo; read the page, don't guess |
| Inspect real Zalo payloads | `scripts/zalo_poll.py` + DB `inbound_messages.payload` | Not an MCP — the real source |

Not needed here: playwright (no UI in this repo — dashboard is a separate web repo), firecrawl, design MCPs.
Record any new MCP this project relies on in `.claude/system-design/integrations.md`.
