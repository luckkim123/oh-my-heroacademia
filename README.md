# omha — oh-my-heroacademia

omha is a **declarative harness registry**: it describes the work-style harnesses
available to a Claude Code session — superpowers and oh-my-claudecode (OMC) — as
A2A agent cards (`cards/<name>.json`). The **Claude Code session itself reads
these cards and does the routing** (LLM judgment). There is no server.

It also doubles as the personal **heroacademia marketplace** root
(`.claude-plugin/marketplace.json`), the successor to claude-settings for owning
and distributing personal plugins (e.g. oh-my-docs).

## Status

v0.2.0 — cards-not-server. The HTTP server and keyword scorer of v0.1.0 were
removed: the routing brain is the Claude Code session (LLM), and the cards are
the data it reads. See the design doc below.

## Routing model — 3-tier fallback cascade

Every non-trivial decision passes through routing once:

1. **SP / OMC** (work-style harnesses, this registry's cards) — pick the fitting one.
2. **Installed domain skills** (oh-my-docs, ppt-academic, gen-image, …) — when no
   harness fits. These are reached as Claude Code skills, not omha cards.
3. **Claude Code direct** — when neither applies.

## What's here

| Path | Role |
|------|------|
| `cards/superpowers.json`, `cards/omc.json` | Work-style harness cards (A2A AgentCard schema) — the routing registry |
| `src/omha/registry.py` | `load_cards()` — loads & validates `cards/*.json` as A2A AgentCards |
| `.claude-plugin/marketplace.json` | heroacademia marketplace (own-code plugins, e.g. oh-my-docs) |

## How to add a harness

Drop a new file at `cards/<name>.json` following the A2A AgentCard schema. No core
code change required — `load_cards()` reads every `*.json` in `cards/`. The
`tags` and `examples` in the card are the routing signals the session reads.

## Design docs

- `/Users/kimseungmin/Desktop/workspace/00-09_Meta/02_Decisions/2026-05-28-omha-redesign-cards-not-server.md` (current — v2)
- `/Users/kimseungmin/Desktop/workspace/00-09_Meta/02_Decisions/2026-05-27-omha-design.md` (v1, server era — superseded §1.3/1.4)
