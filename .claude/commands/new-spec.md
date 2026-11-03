---
description: Start a spec for a roadmap phase or feature, prefilled from the proposal
argument-hint: <phase number or feature name>
---

Create a new spec for: $ARGUMENTS

1. Read `.claude/specs/_TEMPLATE-spec.md`, `.claude/specs/STATUS.md`, and the matching parts of
   `docs/storagemate-proposal-plan-v2.md` (Roadmap theo pha + the flows/sections this work touches).
2. If a spec for this already exists in `.claude/specs/`, open it instead of creating a duplicate.
3. Write `.claude/specs/<today YYYY-MM-DD>-<kebab-name>-spec.md` from the template:
   - Context, Goals, Non-goals taken from the proposal (cite section names), not invented.
   - List "System-design docs this will change" now.
   - Leave "Design summary" for the brainstorm step.
4. Add a 🔲 row to `.claude/specs/STATUS.md`.
5. Stop and suggest running superpowers:brainstorming on it. Do not write code.
