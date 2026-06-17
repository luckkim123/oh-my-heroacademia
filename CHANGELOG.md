# Changelog

## 0.7.1 — 2026-06-17
### Fixed
- **ANALYZE/ROUTE output order made unambiguous.** The 0.7.0 instruction said
  "emit ANALYZE before ROUTE" but every other routing block (`<oms-routing>`,
  `<omd-routing>`, the omha body) says "emit ROUTE at the very front", and the
  model resolved the conflict by putting ROUTE first and ANALYZE below it. The
  closing instruction now explicitly states **ANALYZE sits above ROUTE** and that
  this order overrides the "ROUTE at the front" wording when the gate applies.
  Removed the ambiguous "맨 앞에 이 한 줄로" phrasing that fed the conflict.
  Added a test asserting the explicit ordering clause is present.

## 0.7.0 — 2026-06-17
An analyze-before-route release: the routing hook now asks for a one-shot
requirements analysis *before* the ROUTE line, so the lane verdict and the work
that follows are grounded in a decomposed reading of the request instead of a
raw guess.

### Added
- **`ANALYZE → … then ROUTE` in `route_emit.py`.** The injected checkpoint now
  instructs a requirements decomposition (목적 / 핵심 요구 / 제약 / 모호한 점)
  to be emitted *before* the ROUTE line. Routing and execution are based on that
  analysis — the goal is to finish in one pass instead of misreading the request
  and burning tokens on a rollback.
  - **Gated to 3+ actions / multi-file / ambiguous requests only.** Simple,
    unambiguous 1–2 action requests skip ANALYZE and emit ROUTE directly — the
    analysis itself costs output tokens, so forcing it on trivial asks would
    invert the token-saving intent. Same gate omha already uses for the ROUTE
    verdict.
  - **Ambiguity halts before work.** If the `모호한 점` field is anything other
    than "없음", the model must confirm with the user *before* proceeding to
    ROUTE/execution — this is the actual lever that prevents misunderstand-then-redo.

## 0.6.0 — 2026-06-05
A routing-model release: the cascade grows from "work-style lanes only" into a
three-axis model — **governance (omp) → content domains (oms/omd) → work-style
(omc/sp/omx)** — and three sibling harnesses (omx, oms, omd, omp) become
first-class routing cards instead of demoted 2nd-tier installed skills.

### Added
- **Governance axis — `cards/omp.json` (lane_type `governance`), judged FIRST.**
  oh-my-project (project-folder structure / placement / `.omp` rules) was absent
  from the omha cascade entirely: the ROUTE enum is generated from `cards/*.json`
  names, so with no card, structure/placement work had no lane and fell through to
  handle-directly. Governance is an axis *orthogonal* to the content domains — the
  same `.pptx` is omd when you author its content but omp when you ask whether it
  sits in the right folder — so a two-box (domain vs work-style) split could not
  place it. The card draws the omd/oms boundary explicitly (content authoring =
  oms/omd, folder placement/rules = omp) and names the `.omp/` index-coherence and
  safe-fileops guards that live only inside omp.
- **`oh-my-experiments` (omx) as a 3rd work-style lane** — `cards/omx.json`,
  glob-discovered by `route_emit.py` and `registry.py`, added to the ROUTE verdict
  enum. Distribution stays in OMX's own `omx` marketplace (no dual-publish here).
- **Domain-first routing cards — `cards/oms.json`, `cards/omd.json` (lane_type
  `domain`).** Paper (.tex/.bib → oms) and document (.pptx/.docx/.xlsx/.hwpx → omd)
  work is now enforced at the 1st tier instead of being a 2nd-tier installed-skill
  fallthrough — so "paper work must always enter oms" (where the citation guard
  lives) holds at the routing layer.
- **Marketplace registrations**: `oh-my-project` and `oh-my-experiments` added as
  github-source plugins alongside oh-my-docs / oh-my-scholar, so all siblings
  install the same way.
- **Re-routing clause: push heavy research to OMC** — the hook now advises that
  heavy literature / external-repo / library research be delegated to OMC research
  skills (`external-context` for outward web/docs/GitHub, `sciomc` for deep target
  analysis) rather than a single ad-hoc search. Injects a routing *rule*, not card
  knowledge (no-drift principle holds); preserves the "no OMC parallel for
  citation-bound paper research" guard.

### Changed
- **`hooks/route_emit.py`: 3-way `lane_type` split** (governance / domain /
  work-style). Cards are sorted into three boxes; the cascade is rewritten
  governance-first → domain → work-style. Unknown `lane_type` still falls to
  work-style, so the existing cards stay valid (backward compatible).
- **`cards/{omc,superpowers,omx}.json` → `lane_type: work-style`;
  `cards/{oms,omd}.json` → `domain`; `cards/omp.json` → `governance`.**
- **`registry.py`: `AgentCard` reads `lane_type`** (default `work-style` for
  backward compat).
- **`cards/omx.json` description = commitment to act, not a label** — declaring
  `ROUTE → oh-my-experiments` now obliges actually invoking an omx skill / the
  `.omx` engine, symmetric with how omc/sp enforce route→invoke (closes the
  hand-reading-TensorBoard anti-pattern, caught twice 2026-06-05).
- **README "Routing model"** rewritten from the old 3-tier (SP/OMC → installed
  domain skills → direct) to the governance→domain→work-style cascade with all
  current lanes named.

### Verification
- `route_emit.py` emits a valid `UserPromptSubmit` envelope; the ROUTE enum now
  includes `oh-my-project`, and the governance box renders above the domain box
  (checked by running the hook on `{}` stdin).
- Domain-first routing tests: `tests/test_domain_first_routing.py` (7) — domain
  cards present, lane_type assignment, extension triggers, domain-first context.
- 54 green at the domain-first cascade commit (`5793265`).

### Notes
- omp was already published (`luckkim123/oh-my-project`) and routed via its own
  `UserPromptSubmit` STAGE hook before this release; what 0.6.0 adds is its
  *omha-level* lane card, so the meta-router stops dropping governance work to
  handle-directly.
- The cache copy is pinned to a `gitCommitSha` in `installed_plugins.json`;
  picking up these cards on a machine requires a plugin update/reinstall (the
  marketplace `git pull` alone updates the marketplace mirror, not the live cache).

## 0.5.0 — 2026-05-29
### Added
- **Push channel: `PreToolUse` hook for cross-lane signal detection.** A new `hooks/cross_lane_emit.py` runs on every `Write` / `Edit` / `Skill` tool call, reads `cards/*.json` `triggers` blocks, and emits a hard-toned advisory envelope when the tool target maps to a lane different from what's currently in flight. Tool calls are never blocked — the model sees the advisory in `hookSpecificOutput.additionalContext` and is asked to prepend a STAGE re-route line. Directly addresses the v0.4.0 pull-side gap: even with "re-routing obligation" written into `<omha-routing>`, the model can miss mid-task transitions when context grows long. The push channel turns that from a self-discipline rule into an objective hook firing.
- **`triggers` block on AgentCard.** Cards may now declare `triggers.extensions[]` and `triggers.skills[]` — the push hook's opt-in registry. Backwards-compatible: cards without `triggers` route via pull only (push stays silent). SP/OMC cards now declare their characteristic skill names (writing-plans, test-driven-development, ultrawork, ralph, …). Extensions list is empty on work-style lanes by design — file extensions belong to domain cards (OMD/OMS/…).
- **Stateless 30-second same-lane cooldown** via `/tmp/omha_last_push.json`. Five consecutive `.pptx` writes inside an OMD task emit once, not five times (no token-flood). A lane switch mid-stream re-emits immediately — the transition is the strong signal worth surfacing. Fail-open on corrupt JSON.
- Tests: 30 new across hook + integration (signal extraction, lane matching, cooldown, fail-open, 4 plan §7.2 scenarios A/B/C/D, real SP/OMC card e2e through the hook). 11→47 green.

### Changed
- `src/omha/registry.py`: `AgentCard` gains an optional `triggers: AgentTriggers` field (also dev/CI-time only; the runtime hooks read cards with stdlib `json.loads`).
- `.claude-plugin/plugin.json`: `hooks.PreToolUse` registered alongside the existing `UserPromptSubmit`. Matcher `Write|Edit|Skill` only — `Read` floods (routine scans), `Bash` would need command parsing.

### Verification
- pytest: 47 green on Python 3.9 (was 11; +36 across schema, hook unit, plugin manifest, integration scenarios).
- Hook is stdlib-only — `test_hook_has_no_third_party_imports` enforces it.
- Fail-open paths covered: missing cards dir, corrupt cooldown JSON, garbage stdin, missing `tool_input` keys → exit 0 silent (never blocks a tool call).
- Live `claude -p` validation deferred to the install/marketplace cycle (separate session); the integration tests fully cover the four user-facing scenarios with fixture cards, so the mechanism is proven before deploy.

### Notes
- **Push is opt-in per card.** A card without `triggers` (legacy or by choice) gets pull routing only. Local skills not declared in any card stay in pull's domain — the model still sees them via the skill's own SKILL.md.
- SP/OMC cards declare push `skills` but no `extensions` — extensions are a *domain* concept (which file format) and SP/OMC are *work-style* lanes. Real domain push (OMD `.pptx`, OMS `.tex`, …) requires those plugins to ship cards with `triggers.extensions`; that's a separate, plugin-side change.
- Python 3.10 union syntax (`X | None`) avoided; `Optional[X]` used throughout for 3.9 compatibility (the registry promise).
- Design: `2026-05-29-omha-self-rerouting-design.md` (decisions + dialogue trail). Execution plan: `2026-05-29-omha-self-rerouting-execution.md`.

## 0.4.1 — 2026-05-28
### Changed
- **a2a-sdk dependency removed — omha is now fully dependency-free.** `0.3.0` declared "zero runtime deps — no a2a-sdk", but `src/omha/registry.py` still did `from a2a.types import AgentCard`, so on a Python 3.9 box (a2a-sdk requires ≥3.10) test collection failed. `registry.py` now validates cards with stdlib `dataclasses` (same `.name`/`.skills[].tags|examples` API the tests use), so the declared intent is realized in code. `pyproject.toml`: `dependencies = []`, `requires-python = ">=3.9"`.
- **`ROUTE →` one-liner: emoji removed.** The injected routing line is now plain text `ROUTE → …` (was `🧭 ROUTE → …`), matching the new omd `STAGE(docs) →` / oms `STAGE(paper) →` lines — text labels distinguish the layers, no emoji. (User request: no emoji.)
### Verification
- pytest: 11 green on Python 3.9 (was 2 collection errors from the missing a2a import). registry imports with no third-party deps.
### Notes
- Runtime path was always a2a-free (the hook reads cards with `json.loads`); this change removes the dev/CI-time a2a dependency too, so the whole repo runs anywhere Python 3.9+ is present.

## 0.4.0 — 2026-05-28
### Added
- **Cross-lane re-routing obligation**: the `<omha-routing>` hook context now states that even while working inside a tier-2 domain skill (OMD, slides, …), a heavy subtask that belongs to a work-style lane (parallel multi-source research, deep investigation, test-first code) must trigger a fresh lane judgment on the spot — not be handled inline. Includes a trivial guard (3-4 line fact checks stay direct, no over-attraction) and a citation guard (paper research is done but never with OMC parallelism). Directly fixes the reported symptom: "while OMD is loaded, work that needs OMC for research was just handled inline instead of routing to OMC."
- **Full 3-tier cascade in the hook text**: the injected context now spells out all three tiers (1: SP/OMC lanes → 2: installed domain skills → 3: handle-directly). Previously the hook only named tier-1 and tier-3, so the tier-2 domain layer that the v0.2.0 redesign defined was missing from what the session actually saw.
- `domain-skill` added as a fourth choice in the `🧭 ROUTE →` one-liner (was `oh-my-claudecode|superpowers|handle-directly`), so the session can declare "handling in a domain skill" — the prerequisite for then re-routing out of it.
- Tests: `test_context_states_three_tier_cascade`, `test_context_states_reroute_obligation` (TDD — written failing first, then the hook text was extended to pass).
### Changed
- `hooks/route_emit.py` `build_routing_context()` text only (cards untouched). Knowledge stays in `cards/*.json` (SSOT); the new text is cascade *procedure*, not lane identity, so no card duplication / drift.
### Verification
- pytest: 11 tests green (was 9; +2 new route_emit tests).
- Clean `claude -p` routing (legacy claude-settings routing already removed from live settings; omha is the sole router), loaded via `--plugin-dir` against the uncommitted source:
  - **cross-lane** "parallel research during slide work" → `ROUTE → oh-my-claudecode` (and the session applied the citation guard itself). The core target case.
  - **trivial** "one-line fact insert during slide work" → `ROUTE → handle-directly` (no over-attraction).
  - **regression** "rename across 20 files" → `ROUTE → oh-my-claudecode · ultrawork`; "root-cause-first bug" → recognized systematic-debugging (SP). No entry-routing regression.
- Cards were **not** tuned: the hook change alone resolved cross-lane, so card `examples` were left untouched to avoid the over-attraction regression (9/12) the v0.2.0 redesign measured.
### Notes
- This is the narrow *reverse* slice of the deferred stage-3 cross-lane distribution (domain → work-style re-routing), not the full split/order/merge/failure orchestration — that stays deferred (YAGNI). Design: `2026-05-28-omha-cross-lane-routing-design.md`.
- OMD's own `<Self_Sufficiency>` wording (`~/oh-my-docs/.../docs-pilot/SKILL.md`) was left unchanged: the omha-side fix resolves the symptom from above, per the design's "verify omha alone first" path. Revisit only if measurement later shows the OMD wording suppresses re-routing.

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
- omha A2A HTTP server (stage-1 verdict-type router).
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
