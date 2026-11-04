# System Design — index & freshness

**Claude: read THIS file first, then open only the docs your task touches.**
These docs hold the *why* and the *cross-cutting shape* of the system — the parts a code
knowledge graph cannot see. The graph (graphify) covers the *static structure*: call/import
edges, god nodes, ownership. Use both: graph for "who calls X", these docs for "why is it like this".

## Freshness table
Bump `last-updated` whenever you change a file. A task is not ✅ until the docs it affected are true again.

| File | Purpose | Tier | last-updated |
|------|---------|------|--------------|
| overview.md | What the system is, who it's for, the north star | core | `2026-11-01` |
| architecture.md | C4 view: context → containers → components | core | `2026-11-01` |
| database-design.md | Schema, ERD, relationships, invariants | core | `2026-11-04` |
| directory-map.md | What each folder does, module boundaries, "don't touch" | core | `2026-11-01` |
| data-flow.md | The 8 runtime flows (linking, main message path, confirm/cancel, Q&A, reports, flywheel) | runtime | `2026-11-02` |
| api-contracts.md | Internal endpoints, Zalo Bot API + error handling, webhook payload | surface | `2026-11-02` |
| integrations.md | Zalo, LLM, HF Hub, ngrok, Vercel; env var names; Phase 0 open questions | surface | `2026-11-02` |
| deployment.md | Laptop Compose + ngrok, Vercel, CI/CD, rollback | surface | `2026-11-02` |
| conventions.md | Code discipline (KISS/SOLID), naming, errors, testing, security invariants | intent | `2026-11-01` |
| decisions/ | ADRs 0001–0007 — channel, queue, identity, ledger, parser, hosting | intent | `2026-11-02` |
| glossary.md | VN domain terms ↔ code names | support | `2026-11-02` |

Full proposal (human source, Vietnamese): `docs/storagemate-proposal-plan-v2.md`. These docs summarize it for agents.

## The three layers of "understanding" (why these files exist)
1. **Static structure** — `architecture.md`, `directory-map.md`, `database-design.md`. Graphify auto-covers symbols/edges; these hold human-level boundaries & responsibility.
2. **Runtime behaviour** — `data-flow.md`. What the graph can't capture: how the pieces talk at runtime.
3. **Intent & constraints** — `decisions/`, `conventions.md`. Stops the agent from "helpfully" undoing deliberate choices.

## Diagrams
Prefer Mermaid fenced blocks (```mermaid) so they render in Markdown and Claude can read them as text.
