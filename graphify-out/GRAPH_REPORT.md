# Graph Report - storagemate-service  (2026-11-01)

## Corpus Check
- 106 files · ~8,954 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 372 nodes · 317 edges · 86 communities (26 shown, 60 thin omitted)
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `ef41e949`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- FastAPI
- allow
- storagemate-service
- env.py
- Conventions & Invariants
- Python + FastAPI coding style (storagemate-service)
- config.py
- storagemate-service — Claude Code guide
- Spec: <title>
- Database Design
- Memory — graphify (codebase knowledge graph)
- Architecture
- Deployment
- Overview
- conftest.py
- Skills & Plugins ROUTER — what to use, and when
- API Contracts
- 0001. Record architecture decisions
- Directory Map
- Integrations
- MCP ROUTER — which server for the project at hand
- System Design — index & freshness
- anyio
- Data Flow
- Architecture Decision Records (ADRs)
- worker.py
- auth/__init__.py
- auth/schemas.py
- security.py
- auth/service.py
- base.py
- channels/__init__.py
- web.py
- zalo.py
- zalo_client.py
- chat/__init__.py
- chat/schemas.py
- chat/service.py
- confirm.py
- inventory/__init__.py
- ledger.py
- inventory/schemas.py
- inventory/service.py
- items/__init__.py
- items/schemas.py
- items/service.py
- labels/__init__.py
- labels/schemas.py
- labels/service.py
- dispatcher.py
- messaging/__init__.py
- queue.py
- parser/__init__.py
- llm.py
- ner.py
- regex.py
- parser/service.py
- validate.py
- qa/__init__.py
- prompts.py
- qa/service.py
- tools.py
- reports/__init__.py
- jobs.py
- reports/schemas.py
- reports/service.py
- staff/__init__.py
- staff/schemas.py
- staff/service.py
- STATUS.md
- glossary.md
- build_catalog.py
- evaluate.py
- export_onnx.py
- generate_synthetic.py
- train_ner.py
- create_admin.py
- seed_items.py
- zalo_poll.py
- zalo_set_webhook.py
- tests/__init__.py
- test_inventory.py
- test_parser.py
- test_webhook.py
- storagemate-service

## God Nodes (most connected - your core abstractions)
1. `storagemate-service` - 12 edges
2. `Python + FastAPI coding style (storagemate-service)` - 11 edges
3. `allow` - 10 edges
4. `storagemate-service — Claude Code guide` - 9 edges
5. `get_current_user()` - 8 edges
6. `Spec: <title>` - 8 edges
7. `Conventions & Invariants` - 8 edges
8. `Database Design` - 8 edges
9. `2. Cài đặt từng bước` - 7 edges
10. `Memory — graphify (codebase knowledge graph)` - 6 edges

## Surprising Connections (you probably didn't know these)
- None detected - all connections are within the same source files.

## Import Cycles
- None detected.

## Communities (86 total, 60 thin omitted)

### Community 0 - "FastAPI"
Cohesion: 0.09
Nodes (26): APIRoute, 🖥️ Gom router của các domain mà dashboard gọi. main.py mount api_router với…, get_current_user(), 🖥️ get_current_user: đọc JWT từ header Authorization của UI, gắn vào router cần…, TODO Pha 4: nhận token = Depends(oauth2_scheme), giải mã JWT, trả admin hiện…, 🖥️ /api/auth — UI gọi để đăng nhập., ⚡ /webhooks/zalo — Zalo gọi, KHÔNG phải UI., 🖥️ /api/chat — UI web chat demo. (+18 more)

### Community 1 - "allow"
Cohesion: 0.10
Nodes (20): model, permissions, allow, ask, $schema, statusLine, command, type (+12 more)

### Community 2 - "storagemate-service"
Cohesion: 0.10
Nodes (19): ml/ — train NER (chạy trên máy local RTX 4070, không deploy), 10. Quy trình đóng góp, 1. Yêu cầu, 2. Cài đặt từng bước, 3. Chạy bằng Docker Compose, 4. Lệnh thường dùng, 5. Biến môi trường, 6. Cấu trúc thư mục (+11 more)

### Community 3 - "env.py"
Cohesion: 0.11
Nodes (10): Alembic env: lấy DATABASE_URL từ app/config.py, metadata từ app/models.py., Bảng admins (id, email, password_hash, created_at). Tạo admin bằng…, Bảng inventory_log (sổ cái, chỉ thêm), pending_actions (chờ OK/Sai) và view…, Bảng items (id, name, base_unit, aliases, min_stock) và units (id, item_id,…, Bảng training_samples (id, raw_message, labels, parser_source, verified,…, Bảng inbound_messages (UNIQUE(channel, message_id)) và outbound_messages., Base, Base SQLAlchemy dùng chung + quy ước đặt tên index/constraint (để Alembic sinh… (+2 more)

### Community 4 - "Conventions & Invariants"
Cohesion: 0.14
Nodes (13): Code discipline, Code style, Conventions & Invariants, Error handling, Git & commits, Goal-driven execution, KISS — Keep It Simple, Stupid, Naming (+5 more)

### Community 5 - "Python + FastAPI coding style (storagemate-service)"
Cohesion: 0.17
Nodes (11): 10. Style details, 1. Tooling (enforced by CI), 2. Project layout (domain-first — fastapi-best-practices), 3. Routes, 4. Pydantic v2, 5. SQLAlchemy 2.0, 6. Errors, 7. Config, secrets, logging (+3 more)

### Community 6 - "config.py"
Cohesion: 0.20
Nodes (7): Settings chung, đọc từ biến môi trường / file .env (pydantic-settings). Domain…, Settings, get_db(), Kết nối PostgreSQL bằng SQLAlchemy 2.0 (sync, driver psycopg 3). Route dùng…, Dependency: mỗi request một session, tự đóng khi xong., BaseSettings, Session

### Community 7 - "storagemate-service — Claude Code guide"
Cohesion: 0.20
Nodes (9): 1. What this is, 2. Read order at the start of a task, 3. Model policy, 4. Workflow gates (do not skip), 5. Spec + system-design discipline (this keeps the docs alive), 6. Cost discipline, 7. Hard rules, 8. Stack (+1 more)

### Community 8 - "Spec: <title>"
Cohesion: 0.22
Nodes (8): Context / problem, Design summary, Goals, Non-goals, Spec: <title>, System-design docs this will change, Tasks, Test / acceptance criteria

### Community 9 - "Database Design"
Cohesion: 0.22
Nodes (8): Database Design, Engine & access, ERD, Indexing & performance notes, Invariants & constraints, Migrations, Relationships & cardinality, Tables / entities

### Community 10 - "Memory — graphify (codebase knowledge graph)"
Cohesion: 0.29
Nodes (6): Division of labour, Keep it fresh, Memory — graphify (codebase knowledge graph), One-time GLOBAL setup (do this before anything else), Per project, Query instead of grep

### Community 11 - "Architecture"
Cohesion: 0.29
Nodes (6): Architecture, Communication patterns, Cross-cutting concerns, L1 — Context (system + the world around it), L2 — Containers (deployable/runnable units), L3 — Components (inside a container)

### Community 12 - "Deployment"
Cohesion: 0.29
Nodes (6): CI/CD, Deploy steps, Deployment, Environments, Rollback, Secrets management

### Community 13 - "Overview"
Cohesion: 0.29
Nodes (6): Overview, Scope / non-goals, System context (one glance), The problem & the north star, What it is, Who it's for

### Community 14 - "conftest.py"
Cohesion: 0.40
Nodes (5): AsyncClient, fixture, anyio_backend(), client(), Fixture dùng chung: client async gọi thẳng vào app (httpx + ASGITransport),…

### Community 15 - "Skills & Plugins ROUTER — what to use, and when"
Cohesion: 0.33
Nodes (5): Gate → skill map (the harness), How to extend, "Kit" toolkit skills (bundled/global, installed in `~/.claude/skills`), Skills & Plugins ROUTER — what to use, and when, Stack snippet skills (per-project, inserted via `/init-project`)

### Community 16 - "API Contracts"
Cohesion: 0.33
Nodes (5): API Contracts, Auth model, Conventions, Endpoints, Spec source

### Community 17 - "0001. Record architecture decisions"
Cohesion: 0.33
Nodes (5): 0001. Record architecture decisions, Alternatives considered, Consequences, Context, Decision

### Community 18 - "Directory Map"
Cohesion: 0.33
Nodes (5): Directory Map, "Don't touch" zones, Module boundaries, Ownership, Top-level layout

### Community 19 - "Integrations"
Cohesion: 0.33
Nodes (5): Env vars (names + where they live), External services, Integrations, MCP servers used in dev, Webhooks / callbacks

### Community 20 - "MCP ROUTER — which server for the project at hand"
Cohesion: 0.40
Nodes (4): Decide by project type, MCP ROUTER — which server for the project at hand, Setup, Task → MCP map

### Community 21 - "System Design — index & freshness"
Cohesion: 0.40
Nodes (4): Diagrams, Freshness table, System Design — index & freshness, The three layers of "understanding" (why these files exist)

### Community 22 - "anyio"
Cohesion: 0.67
Nodes (3): anyio, test_health(), test_openapi_has_api_prefix()

### Community 23 - "Data Flow"
Cohesion: 0.50
Nodes (3): Data Flow, Flow: <!-- add more as needed -->, Flow: <!-- e.g. User sign-in -->

### Community 24 - "Architecture Decision Records (ADRs)"
Cohesion: 0.50
Nodes (3): Architecture Decision Records (ADRs), Index, New ADR — copy this

## Knowledge Gaps
- **129 isolated node(s):** `$schema`, `model`, `type`, `command`, `Read` (+124 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **60 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What connects `$schema`, `model`, `type` to the rest of the system?**
  _129 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `FastAPI` be split into smaller, more focused modules?**
  _Cohesion score 0.08502024291497975 - nodes in this community are weakly interconnected._
- **Should `allow` be split into smaller, more focused modules?**
  _Cohesion score 0.09523809523809523 - nodes in this community are weakly interconnected._
- **Should `storagemate-service` be split into smaller, more focused modules?**
  _Cohesion score 0.09523809523809523 - nodes in this community are weakly interconnected._
- **Should `env.py` be split into smaller, more focused modules?**
  _Cohesion score 0.10526315789473684 - nodes in this community are weakly interconnected._
- **Should `Conventions & Invariants` be split into smaller, more focused modules?**
  _Cohesion score 0.14285714285714285 - nodes in this community are weakly interconnected._