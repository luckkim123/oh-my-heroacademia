# Changelog

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
