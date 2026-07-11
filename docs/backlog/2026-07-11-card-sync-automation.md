# Backlog: card-sync automation (mechanical drift check)

**Filed**: 2026-07-11, during omp Release 2 Task 7 (0.5.0 `handoff` stage card sync).

## Problem

`cards/omp.json` is a manual mirror of the sibling `oh-my-project` repo's `plugin.json` `skills[]`
list. Every time omp adds a stage, someone has to remember to also update this card's
`triggers.skills`, the skill entry's STAGE enumeration in its `description`, `tags`, and
`examples` — by hand, in a separate repo, in a separate PR.

Measured pain: ~12 of the last 20 omha commits were card/text sync commits, and each omp
stage-sync PR (e.g. `omp-card-secretary-040`, this one) touches roughly 12 manual sync points
across `cards/omp.json` alone (version, top-level description mention, skill description STAGE
list, `triggers.skills` array, plus tags/examples additions). Nothing catches it mechanically if
a sync is missed — drift is silent until someone notices a stage that doesn't route.

## Prescription (§12.3)

Add a card-sync check: compare each sibling plugin's `plugin.json` `skills[]` against the
matching `cards/<name>.json` `triggers.skills`, and fail (pytest or a standalone script) if the
two sets diverge. This turns "did someone forget to sync the card" from a manual-recall problem
into a CI-caught one.

## Scope note

Implementation of the check itself is out of scope for omp — it belongs to omha, since the card
format and the sibling-repo comparison logic both live here. This note only records the
prescription and the measured pain; no code change accompanies it.
