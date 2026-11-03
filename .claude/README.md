# .claude/ — agent workspace for storagemate-service

| Path | What |
|------|------|
| `CLAUDE.md` | Always-loaded map + hard rules |
| `system-design/` | Architecture, DB, flows, API, integrations, deployment, ADRs — start at its `README.md` |
| `specs/` | One spec per task + `STATUS.md` board; `/new-spec` creates one |
| `rules/python-fastapi.md` | Coding rules, auto-loaded for `*.py` |
| `skills/ROUTER.md` · `mcp/ROUTER.md` | Which skill / MCP for which task |
| `commands/` | Project slash commands |
| `memory/README.md` | graphify setup and queries |
| `settings.json` | Shared permissions (`.env` is denied) · `settings.local.json` = personal, gitignored |

Scope source of truth: `docs/storagemate-proposal-plan-v2.md` (Markdown of the proposal .docx).
