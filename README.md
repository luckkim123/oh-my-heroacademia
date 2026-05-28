# omha — oh-my-heroacademia

omha is a **declarative harness registry**: it describes the work-style harnesses
available to a Claude Code session — superpowers and oh-my-claudecode (OMC) — as
A2A agent cards (`cards/<name>.json`). The **Claude Code session itself reads
these cards and does the routing** (LLM judgment). There is no server.

It also doubles as the personal **heroacademia marketplace** root
(`.claude-plugin/marketplace.json`), the successor to claude-settings for owning
and distributing personal plugins (e.g. oh-my-docs).

## Status

v0.4.0 — **cross-lane re-routing + full 3-tier cascade in the hook.** The
`UserPromptSubmit` hook now injects all three cascade tiers (was only tier-1/tier-3)
plus a **re-routing obligation**: even while working inside a tier-2 domain skill
(OMD, slides, …), if you hit a heavy subtask that belongs to a work-style lane
(parallel research, deep investigation, test-first code), re-judge the lane on the
spot. Trivial checks stay direct; citation-bound (paper) research is done but never
with OMC parallelism. The Claude Code session (LLM) does the judgment; the hook only
feeds it the cards. No server (removed in v0.2.0).

## Prerequisites

omha **routes** to lanes; it does not bundle or install them. Claude Code plugins
have no dependency declaration, so you must install the lane harnesses yourself
**before** omha is useful — otherwise omha will route a request to a lane whose
skills are not present:

```bash
# superpowers (the "discipline" lane)
claude plugin install superpowers@claude-plugins-official

# oh-my-claudecode (the "throughput/autonomy" lane)
claude plugin marketplace add Yeachan-Heo/oh-my-claudecode
claude plugin install oh-my-claudecode@omc

# then omha itself
claude plugin marketplace add https://github.com/luckkim123/oh-my-heroacademia.git
claude plugin install oh-my-heroacademia@heroacademia
```

With neither lane installed, omha degrades to "handle-directly" for everything —
harmless, but pointless. Installing one lane (just SP, or just OMC) is fine; omha
will simply never route to the missing one.

## Routing model — 3-tier fallback cascade

The hook injects this every turn; the session decides:

1. **SP / OMC** (work-style harnesses, this registry's cards) — pick the fitting lane.
2. **Installed domain skills** (oh-my-docs, ppt-academic, gen-image, …) — when no
   harness lane fits. Reached as Claude Code skills, not omha cards.
3. **Claude Code direct** — when neither applies (trivial / single-file).

**Re-routing obligation (v0.4.0).** Routing is not a one-time gate at entry. While
inside a tier-2 domain skill, a heavy subtask that is essentially a work-style lane
job — parallel multi-source research, deep investigation ("why did this happen"),
test-first code — must trigger a fresh lane judgment right there, rather than being
handled inline. The threshold matters: a 3-4 line fact check stays direct (no
over-attraction), and citation-bound (paper) research is done but never via OMC
parallelism (hallucination guard). This is what makes "OMD work that needs OMC for
research" actually reach OMC instead of being done inline.

The session names the lane; the *skill* inside that lane is picked by the lane's
own plugin (OMC's keyword-detector, SP's using-superpowers), not by omha. omha
routes lanes, not skills.

## What's here

| Path | Role |
|------|------|
| `hooks/route_emit.py` | `UserPromptSubmit` hook — reads `cards/*.json` (stdlib only, **no a2a-sdk**) and injects the lane-routing checkpoint every turn |
| `cards/superpowers.json`, `cards/omc.json` | Work-style harness cards — the routing registry (single source of truth) |
| `.claude-plugin/plugin.json` | Plugin manifest registering the hook (version omitted → commit-SHA versioning) |
| `.claude-plugin/marketplace.json` | heroacademia marketplace (own-code plugins, e.g. oh-my-docs) |
| `src/omha/registry.py` | `load_cards()` — A2A AgentCard validation, **dev/CI-time only** (the runtime hook does not depend on it) |

## How to add a harness

Drop a new file at `cards/<name>.json`. The hook reads every `*.json` in `cards/`
— no code change. The card's `name` + `description` are the lane signals the
session reads.

## Design docs

- `.../02_Decisions/2026-05-28-omha-stage1-plugin-hook-routing.md` (current — stage-1)
- `.../02_Decisions/2026-05-28-omha-redesign-cards-not-server.md` (v2 — cards-not-server)
- `.../02_Decisions/2026-05-27-omha-design.md` (v1, server era — superseded)
