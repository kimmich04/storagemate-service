# Specs — status board

Every task starts as a spec here. Legend: 🔲 not started · 🟡 in progress · ✅ done · ⏸ paused.
**Rule:** a spec is not ✅ until (a) its task checklist is all checked and (b) the
`.claude/system-design/` docs it affected are updated + re-stamped.

| Spec | Status | Started | Updated | System-design docs touched |
|------|--------|---------|---------|-----------------------------|
| 2026-11-01-phase0-zalo-bot-spec.md | ✅ (field ảnh chưa xác minh → integrations.md) | 2026-11-03 | 2026-11-04 | integrations, data-flow, api-contracts |
| 2026-11-06-phase1-db-ledger-spec.md | 🟡 code + docs xong; Zalo polling ✅ (owner 07/11); còn webhook (invite spec §2.2 W10) | 2026-11-06 | 2026-11-07 | data-flow, database-design, api-contracts, integrations, directory-map, deployment |
| 2026-11-06-phase1-invite-code-spec.md | ✅ 133 test pass; Zalo polling I1–I6 đúng (webhook: §2.2 W1–W10 chờ chạy) | 2026-11-06 | 2026-11-07 | data-flow, database-design, directory-map |
| 2026-11-09-phase2-llm-fallback-spec.md | 🟡 code + docs xong, 152 test pass, Gemini thật ✅; còn chạy thử trên Zalo thật rồi mới ✅ | 2026-11-09 | 2026-11-09 | data-flow, database-design, integrations, directory-map |

## Roadmap (one or more specs per phase — create with `/new-spec <phase>`)
| Phase | Goal | Est. | Spec |
|-------|------|------|------|
| 0 | Zalo Bot: polling echo → webhook + secret; save real payloads; test proactive send | 3–5 d | phase0-zalo-bot |
| 1 | Non-AI ingestion: adapters, queue+dedup, invite codes, regex, validate, ledger + Hủy, reports, catalog + golden set | ~2 w | phase1-db-ledger (queue + ledger); phase1-invite-code; Hủy/reports: chưa có |
| 2 | NER (synthetic BIO, ViDeBERTa-xsmall → ONNX int8) + LLM fallback + OK/Sai | 2–3 w | – |
| 3 | Q&A (tools + SQL agent fallback) + dashboard API, label review, staff/invite | 2–3 w | – |
| Gate | Local E2E on Compose; golden set + Q&A question set pass | – | – |
| 4 | Auth: JWT admin, manager role, invite lockout | ~1 w | – |
| 5 | Deploy: Vercel + Compose on laptop + ngrok + GitHub Actions | ~1 w | – |
| 6 | Flywheel retrain; optional OCR; multi-tenant | ongoing | – |

Short on time (hackathon): demo Phases 0–1 + LLM fallback + simple Q&A; present NER/flywheel as roadmap.
