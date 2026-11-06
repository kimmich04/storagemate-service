# 0007. Host api + worker + DB on a laptop via Docker Compose + ngrok
> Status: Accepted
> Date: 2026-11-01

## Context
Student project, $0 budget, server only needed during test/demo.

## Decision
We will run api, worker and postgres with Docker Compose on Windows (Docker Desktop + WSL 2), exposed through an
ngrok fixed dev domain; dashboard on Vercel; CI on GitHub-hosted runners, CD via a self-hosted runner on push to `main` only.

## Alternatives considered
Render free (512 MB, sleeps, DB expires in 30 days), HF Docker Spaces (now paid), OrbStack (macOS only).

## Consequences
- Laptop off = bot offline; messages may be lost if Zalo doesn't retry (Phase 0 test).
- ngrok free limits (20k req, 1 GB/month) and browser warning header. Self-hosted runner requires a private repo.
