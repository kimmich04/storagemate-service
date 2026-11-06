# 0004. Identify Zalo users by invite-code linking
> Status: Accepted
> Date: 2026-11-01

## Context
Zalo Bot webhooks carry `from.id`, `display_name`, `chat.id` — no phone number, so v1's phone whitelist is impossible.
`display_name` is user-editable. The bot deeplink/QR is public.

## Decision
We will link `staff.zalo_user_id`/`zalo_chat_id` via a 6-char, single-use, 24 h invite code generated on the dashboard.
Unlinked chats can only submit a code; >5 failures in 15 min locks the chat_id.

## Alternatives considered
- Phone whitelist — data not available. Trust `display_name` — spoofable. Open bot — anyone writes fake stock.

## Consequences
- Deeplink/QR only opens the chat; the code is the security boundary.
- Admin must issue a code per staff member (onboarding step).
