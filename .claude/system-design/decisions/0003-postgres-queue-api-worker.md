# 0003. Postgres table as queue; api + worker from one image
> Status: Accepted
> Date: 2026-11-01

## Context
Webhooks must return 2xx fast; parsing (NER/LLM) and replies are slow. Single shop, low volume, one laptop host.

## Decision
We will have `api` verify + normalize + `INSERT … ON CONFLICT (channel, message_id) DO NOTHING` into
`inbound_messages` and return 200. A single `worker` process (same image) claims rows with
`FOR UPDATE SKIP LOCKED`, runs NER in-process (ONNX) and APScheduler. 3 containers: api, worker, postgres.

## Alternatives considered
- Redis/RabbitMQ/Celery — another container for no measured need.
- FastAPI BackgroundTasks — lost on restart, no dedup, no retry state.
- Separate NER service (v1) — merged; split again when worker memory/latency demands it.

## Consequences
- Dedup + durable retry state for free; raw payload kept for debugging.
- Exactly one worker instance, otherwise scheduled reports double-fire.
