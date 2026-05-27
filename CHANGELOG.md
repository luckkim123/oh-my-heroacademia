# Changelog

## 0.3.0 — 2026-05-28
### Added
- **stage-1 lane routing**: `hooks/route_emit.py` — a `UserPromptSubmit` hook that reads `cards/*.json` (stdlib `json` only, **zero runtime deps — no a2a-sdk**) and injects an `<omha-routing>` checkpoint every turn. The Claude Code session (LLM) does the lane judgment; the hook only feeds it the cards.
- `.claude-plugin/plugin.json` — omha is now a Claude Code **plugin** (registers the hook), while still being the heroacademia **marketplace**. Both manifests coexist in `.claude-plugin/`. `version` omitted (commit-SHA versioning).
- Tests: `test_route_emit.py` (context lists each lane + handle-directly; asserts no a2a import), `test_plugin_manifest.py` (hook registration + marketplace/plugin coexistence).
### Changed
- omha is now marketplace + plugin (was marketplace-only). `registry.py` (a2a validation) is now explicitly **dev/CI-time only** — the runtime hook never imports it.
### Verification
- pytest: 9 tests green (smoke, registry, cards_valid, route_emit, plugin_manifest).
- hook CLI: emits valid `UserPromptSubmit` envelope with both lanes.
- a2a isolation: hook runs with `a2a` blocked (runtime dep = 0).
- **Clean live-load routing** (claude-settings routing hooks temporarily OFF so only omha's hook was active, then restored): 4/4 correct on `claude -p` clean sessions — OMC (bulk edit), SP (root-cause-first), handle-directly (typo), domain-skill fallthrough (PPT → ppt-academic, not a lane). Confirms the 3-tier cascade and lane-not-skill granularity work in a real session.
### Notes
- The routing brain is the Claude Code session, not the hook. Cards = single source of truth; the hook reads, never embeds (no drift — the legacy claude-settings SKILL.md↔reminder.py duplication is not reproduced).
- omha's hook and claude-settings' `routing-verdict-reminder.py` both fire during the stage-1 coexistence period. Disabling the legacy claude-settings routing (Strangler Fig step 1 completion) is a separate, user-confirmed claude-settings change.

## 0.2.0 — 2026-05-28
### Removed
- HTTP server (`server.py`) + FastAPI/uvicorn deps + `omha` console entry point.
- Keyword router (`router.py`, `_score`) — routing brain moves to the Claude Code session (LLM), cards are the data it reads.
- `cards/omd.json` — OMD is a document *domain* tool, not a work-*style* harness; it ships via the heroacademia marketplace and is reached as an installed skill, not an omha routing card.
- `tests/test_server.py`, `tests/test_router.py`.
### Changed
- omha is now a declarative harness card registry, not a server. `registry.py` + `cards/*.json` (SP/OMC) remain; `a2a-sdk` kept (cards validated as A2A AgentCard), FastAPI/uvicorn/httpx dropped.
- Routing model = 3-tier fallback cascade (1: SP/OMC harness cards, 2: installed domain skills incl. OMD/ppt-academic/gen-image, 3: Claude Code direct). See `2026-05-28-omha-redesign-cards-not-server.md`.
- Cards are **harness-unit, not skill-unit**: each card describes the harness's lane identity + domain boundary + representative signals, not a full skill catalog (that stays in claude-settings `using-omc`, to avoid DRY violation and signal over-attraction). Verified on clean `claude -p` sessions: lean harness-unit cards routed 11/12 vs 9/12 for skill-unit cards (the one miss was LLM non-determinism, not a card defect).
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
