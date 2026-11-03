# 0001. Record architecture decisions
> Status: Accepted
> Date: —

## Context
We need to remember *why* structural choices were made, so future work (human or agent)
doesn't silently undo them. Memory across sessions is expensive; a durable, versioned record is cheap.

## Decision
We will keep ADRs in `.claude/system-design/decisions/`, numbered and immutable once Accepted.
Reversing a decision means writing a new ADR that supersedes the old one.

## Alternatives considered
- Only commit messages: too scattered, no rationale.
- A wiki: drifts from the repo, not in the agent's read path.

## Consequences
- Every non-obvious choice has a home.
- The agent reads intent instead of re-deriving it.
