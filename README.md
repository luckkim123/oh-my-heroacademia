# omha — oh-my-heroacademia

omha is a **declarative harness registry**: it describes the work-style harnesses
available to a Claude Code session — superpowers and oh-my-claudecode (OMC) — as
A2A agent cards (`cards/<name>.json`). The **Claude Code session itself reads
these cards and does the routing** (LLM judgment). There is no server.

It also doubles as the personal **heroacademia marketplace** root
(`.claude-plugin/marketplace.json`), the successor to claude-settings for owning
and distributing personal plugins (e.g. oh-my-docs).

## Status

v0.6.0 — **three-axis cascade.** Routing grows from work-style-only into
**governance (omp) → content domains (oms/omd) → work-style (omc/sp/omx)**.
oh-my-project joins as a `governance` lane (judged first, so structure/placement
work stops falling through to handle-directly); oms/omd become first-class
`domain` cards; omx joins as a 3rd work-style lane. See the routing model below.

v0.5.0 — **push channel added: PreToolUse cross-lane signal hook.** Cards now
declare objective push signals (`triggers.extensions[]` / `triggers.skills[]`); a
new `PreToolUse` hook (`Write|Edit|Skill` matcher) reads the *actual tool call
payload* and surfaces lane mismatches the model might otherwise miss inline. Tone
is advisory (asks the model to prepend a STAGE re-route line); the tool call is
never blocked. 30-second same-lane cooldown prevents token-flood on consecutive
operations; lane switches re-emit immediately.

Together with the v0.4.0 pull channel (`UserPromptSubmit` ROUTE injection), omha
now runs a **pull + push** routing model: the pull channel keeps the lane
discipline visible every turn; the push channel catches mid-task transitions
without relying on the model noticing them. Push is opt-in per card — registering
a `triggers` block is the explicit signal "I want hard-pushed onto this lane."

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

## Routing model — three-axis cascade

The hook injects this every turn; the session decides, top-down:

0. **Governance (omp)** — is this about *where* files belong / whether the tree
   obeys its rules (placement, relocation, naming, dataset tracking, `.omp`)?
   This axis is orthogonal to the content domains (the same `.pptx` is omd when
   you author it, omp when you ask whether it sits in the right folder), so it is
   judged first — else structure work falls through to handle-directly.
1. **Content domains (oms / omd)** — is the work product an academic paper
   (.tex/.bib → oms) or a deliverable document (.pptx/.docx/.xlsx/.hwpx → omd)?
   Paper work *must* enter oms, where the citation-integrity guard lives.
2. **Work-style lanes (omc / sp / omx)** — when no domain fits, pick by *how* you
   work: throughput/autonomy (omc), test-first discipline (sp), experiment
   analysis/design (omx).
3. **Claude Code direct** — when none apply (trivial / single-file).

**Re-routing obligation (v0.4.0).** Routing is not a one-time gate at entry. While
inside a content-domain lane, a heavy subtask that is essentially a work-style lane
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
| `hooks/route_emit.py` | `UserPromptSubmit` hook (pull) — reads `cards/*.json` and injects the `<omha-routing>` lane checkpoint every turn |
| `hooks/cross_lane_emit.py` | `PreToolUse` hook (push) — matches `Write\|Edit\|Skill` tool input against `cards/*.json` `triggers` and emits a STAGE re-route advisory on cross-lane transitions (30 s cooldown). Stdlib only |
| `cards/superpowers.json`, `cards/omc.json` | Work-style harness cards — the routing registry (single source of truth). Each card may declare `triggers.{extensions, skills}` for push opt-in |
| `.claude-plugin/plugin.json` | Plugin manifest registering both hooks (version omitted → commit-SHA versioning) |
| `.claude-plugin/marketplace.json` | heroacademia marketplace (own-code plugins, e.g. oh-my-docs) |
| `src/omha/registry.py` | `load_cards()` — AgentCard validation incl. optional `triggers` block, **dev/CI-time only** (the runtime hooks do not depend on it) |

## How to add a harness

Drop a new file at `cards/<name>.json`. Both hooks read every `*.json` in `cards/`
— no code change. The card's `name` + `description` are the pull-side lane
signals the session reads. To opt the new harness into the push channel too, add
a `triggers` block:

```json
{
  "name": "oh-my-newthing",
  "description": "...",
  "skills": [ ... ],
  "triggers": {
    "extensions": [".foo"],
    "skills": ["newthing-build", "newthing-verify"]
  }
}
```

A card without `triggers` (or with empty arrays) routes via pull only — the
push hook stays silent for its tool calls.

## Design docs

- `.../02_Decisions/2026-05-29-omha-self-rerouting-design.md` (current — push channel via PreToolUse)
- `.../02_Decisions/2026-05-28-omha-cross-lane-routing-design.md` (cross-lane re-routing obligation — v0.4.0)
- `.../02_Decisions/2026-05-28-omha-stage1-plugin-hook-routing.md` (stage-1)
- `.../02_Decisions/2026-05-28-omha-redesign-cards-not-server.md` (v2 — cards-not-server)
- `.../02_Decisions/2026-05-27-omha-design.md` (v1, server era — superseded)
