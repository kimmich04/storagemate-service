# 0002. Zalo Bot (1:1) as the primary channel, behind a channel adapter
> Status: Accepted
> Date: 2026-11-01

## Context
v1 used WhatsApp Cloud API. F&B staff in Vietnam already use Zalo; WhatsApp means installing a new app and, from
2026-10-01, paid service messages. Zalo OA needs business verification (4–14 days) and a paid plan (≈99k–399k đ/month).
Zalo Bot is set up in minutes with a personal account but is beta: ≤ 3 bots/account, no buttons, groups not open.

## Decision
We will use Zalo Bot Platform with 1:1 chats only, plus a web chat on the dashboard that goes through the same
pipeline. All channel specifics live in `app/channels/` adapters that emit `InboundMessage`.

## Alternatives considered
- WhatsApp Cloud API — wrong market, pricing change.
- Zalo OA — heavy setup, paid, 48 h/7-day messaging window.
- Zalo group chat — internal beta; bot would only see @mentions/replies.

## Consequences
- Beta risk contained: if rules change, write a Zalo OA adapter; router/parser/DB unchanged.
- No buttons → confirmations are typed `OK`/`Sai`. Payload has no phone → see ADR 0004.
