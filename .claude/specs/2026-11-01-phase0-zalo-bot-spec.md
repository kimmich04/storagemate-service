# Spec: Phase 0 — Zalo Bot setup (polling echo → webhook)
> Status: 🔲 not started · Owner: you · Created: 2026-11-01

## Context / problem
Roadmap Phase 0 (overview.md). Prove the Zalo Bot channel works before building the pipeline; answer the open questions
(proactive send after silence, webhook retry, `date` unit, image field names) with real payloads.

## Goals
- `getMe` succeeds with `ZALO_BOT_TOKEN`; echo bot works via `scripts/zalo_poll.py`
- `POST /webhooks/zalo` verifies `X-Bot-Api-Secret-Token` (403 on mismatch) and stores raw payload
- Real payload samples saved; open questions answered in integrations.md

## Non-goals
- Parser, ledger, invite codes (Phase 1)

## Design summary
<!-- fill after brainstorm -->

## Tasks
- [ ] <!-- step 1 -->
- [ ] <!-- step 2 -->
- [ ] Update affected system-design docs + bump last-updated
- [ ] Update this spec's row in STATUS.md to ✅

## Test / acceptance criteria
<!-- How we know it's done and correct. See engineering:testing-strategy. -->

## System-design docs this will change
<!-- List them now so the "done" gate is unambiguous. -->
