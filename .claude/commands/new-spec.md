---
description: Start a spec for a roadmap phase or feature, prefilled from the proposal
argument-hint: <phase number or feature name>
---

Create a new spec for: $ARGUMENTS

1. Read `.claude/specs/_TEMPLATE-spec-backend.md`, `.claude/specs/STATUS.md`, and the matching parts of
   `docs/storagemate-proposal-plan-v2.md` (Roadmap theo pha + the flows/sections this work touches).
2. If a spec for this already exists in `.claude/specs/`, open it instead of creating a duplicate.
3. Write `.claude/specs/<today YYYY-MM-DD>-<kebab-name>-spec.md` from the template (keep its Vietnamese headings):
   - Mục tiêu + mục 1 Phạm vi taken from the proposal (cite section names), not invented.
   - Fill mục 2–8 as far as the proposal + `system-design/` allow; mark unknowns `<!-- chưa rõ: hỏi owner -->`.
   - List mục 12 "System-design docs sẽ đổi" now.
   - Leave mục 9 "Code từng file" empty and set "Trạng thái code: nháp".
4. Add a 🔲 row to `.claude/specs/STATUS.md`.
5. Stop and suggest running superpowers:brainstorming on it. Do not write code yet.

Later steps (after brainstorm approves the design):
- Look up docs with context7 for every library the spec uses (record them in mục 13), then write the full code of each
  file into mục 9 and the tests into mục 10.
- At implement time, create the files from mục 9, run `ruff check .`, `ruff format --check .`, `pytest`; when they pass,
  change "Trạng thái code" to "đã chạy … pass (<date>)" and sync any fixes back into mục 9.
