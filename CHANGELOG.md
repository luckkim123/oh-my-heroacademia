# Changelog

## 0.2.0 — 2026-05-28
### Removed
- HTTP server (`server.py`) + FastAPI/uvicorn deps + `omha` console entry point.
- Keyword router (`router.py`, `_score`) — routing brain moves to the Claude Code session (LLM), cards are the data it reads.
- `cards/omd.json` — OMD is a document *domain* tool, not a work-*style* harness; it ships via the heroacademia marketplace and is reached as an installed skill, not an omha routing card.
- `tests/test_server.py`, `tests/test_router.py`.
### Changed
- omha is now a declarative harness card registry, not a server. `registry.py` + `cards/*.json` (SP/OMC) remain; `a2a-sdk` kept (cards validated as A2A AgentCard), FastAPI/uvicorn/httpx dropped.
- Routing model = 3-tier fallback cascade (1: SP/OMC harness cards, 2: installed domain skills incl. OMD/ppt-academic/gen-image, 3: Claude Code direct). See `2026-05-28-omha-redesign-cards-not-server.md`.
### Verification
- pytest: smoke + registry + cards_valid — 5 tests, all green.
### Notes
- Rationale: the "server" was justified only by multi-machine federation, which turned out not to be a real requirement (machines sync via iCloud/git, not network calls). v0.1.0 server recoverable from git history (commit c01f95e) if federation is ever needed.

## 0.1.0 — 2026-05-27
### Added
- omha A2A HTTP server (stage-1 판정형 router).
- Declarative card registry (`cards/*.json` -> A2A AgentCard) — new harness = drop a JSON file.
- 3 harness cards: superpowers + oh-my-claudecode (real), oh-my-docs (planned).
- Endpoints: `/harnesses`, `/harness/{name}/.well-known/agent-card.json`, `POST /route`.
- Console entry point: `omha`.
### Verification
- pytest: smoke + registry + cards + router + server — 14 tests, all green.
- Manual: `omha` boots on 127.0.0.1:8973, curl discovery + route verdict confirmed.
### Notes
- Forward/distribution (stage 2-3), auth, remote federation = NOT in this release (server-from-stage-1 by design).
- a2a-sdk pinned >=0.3,<0.4 (built against 0.3.26); re-verify before v1.0 (breaking migration exists).
- Stage-1 router is a deliberately coarse keyword judge; known limitations (punctuation tokenization, common-word example noise) deferred to stage 2.
