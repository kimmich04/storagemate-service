# Memory — graphify (codebase knowledge graph)

Why: instead of re-reading/grepping the repo every session, the agent queries a persistent graph
of the code. Big token savings and answers that trace to real file:line paths. On-device, Apache 2.0.

## One-time GLOBAL setup (do this before anything else)
```
uv tool install graphifyy      # package name has two y's
graphify install               # registers the /graphify skill with Claude Code
```

## Per project
```
/graphify .                    # inside Claude Code — maps this repo into a graph
```
This writes: `graph.json` (the graph), `graph.html` (interactive view), `GRAPH_REPORT.md`
(god nodes, surprising connections, the "why" from NOTE/WHY/HACK comments).

## Query instead of grep
```
graphify query "who owns billing?"
graphify explain <symbol>
graphify path <A> <B>
```
The MCP server can also serve the graph to Claude Code directly.

## Keep it fresh
- Re-run `/graphify .` after big structural changes (or wire a git hook / run weekly).
- `graph.json` and `graph.html` are regenerable → gitignored. You may commit `GRAPH_REPORT.md`
  as a readable snapshot for humans.

## Division of labour
- **graphify** = static structure (symbols, calls, imports, ownership).
- **`.claude/system-design/`** = intent, runtime flows, decisions — the "why" a graph can't hold.
