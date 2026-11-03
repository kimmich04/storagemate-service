# Architecture Decision Records (ADRs)

Short docs capturing *why* a significant choice was made, the alternatives, and the consequences.
Format: Michael Nygard style. One file per decision, numbered. Never edit a decided ADR to reverse it —
write a new one that supersedes it.

## Index
| # | Title | Status | Date |
|---|-------|--------|------|
| 0001 | Record architecture decisions | Accepted | — |
| 0002 | Zalo Bot (1:1) as primary channel, behind a channel adapter | Accepted | 2026-11-01 |
| 0003 | Postgres table as queue; api + worker from one image | Accepted | 2026-11-01 |
| 0004 | Identify Zalo users by invite-code linking | Accepted | 2026-11-01 |
| 0005 | Append-only inventory ledger with reversing rows | Accepted | 2026-11-01 |
| 0006 | Regex-first parser cascade; NER/LLM reads need human OK | Accepted | 2026-11-01 |
| 0007 | Host api + worker + DB on a laptop via Compose + ngrok | Accepted | 2026-11-01 |

Pending (decide later, then write an ADR): LLM provider (Phase 2) · split NER into its own service.

## New ADR — copy this
```
# NNNN. <title>
> Status: Proposed | Accepted | Superseded by NNNN
> Date: YYYY-MM-DD

## Context
What forces are at play (technical, business, constraints).

## Decision
What we decided, in active voice: "We will ...".

## Alternatives considered
What else, and why not.

## Consequences
What becomes easier, what becomes harder, follow-ups.
```
