# 0009. Invite codes do not expire
> Status: Accepted (supersedes the 24 h TTL in 0004)
> Date: 2026-11-15

## Context
ADR 0004 gave invite codes a 24 h lifetime. In practice codes are handed out and used later (new staff start days
after being added; a test reset makes the seed code `TEST01` useless the next day), and an expired code only
produces a generic "mã không đúng" reply and a round trip to the manager. The owner decided codes should not expire.

## Decision
We will create invite codes without an expiry (`invite_codes.expires_at` NULL, migration `0004_invite_no_expiry`).
A code stays valid until it is used once or revoked; creating a new code for the same staff member revokes the old
unused one. The column stays, so a per-code expiry can be set later; a non-NULL past `expires_at` is still rejected.

## Alternatives considered
- Keep 24 h — safest against a leaked code, but the friction above is the common case.
- Longer TTL (7 or 30 days) — still fails for staff added well before their first day; no clear right number.

## Consequences
- A leaked, unused code stays usable until someone uses or revokes it. Mitigations: single use, revoke by issuing a
  new code, `staff.active = false` blocks redemption, and the manager sees who linked in the dashboard.
- Brute force is not limited by time any more; the planned lockout (>5 failures in 15 min per chat, Phase 4) matters
  more and should be built before production.
- The upgrade also clears the expiry of codes that are still waiting to be used.
- Single use stays in production. For local testing only, `INVITE_REUSABLE=true` lets a used code be redeemed
  again (each redemption relinks that staff member to the new chat); default `false`, and the worker logs a warning
  when it is on. Never enable it in production: anyone holding the code could take over that staff account.
