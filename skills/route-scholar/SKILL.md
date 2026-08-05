---
name: route-scholar
description: "Declare this turn's routing lane as oh-my-scholar. The invocation itself is the verdict — it replaces the visible ROUTE line and puts the lane on the HUD."
argument-hint: "<one-line reason for this lane>"
---

# Lane: oh-my-scholar

paper work — research, outline, draft, inspect, verify, mock-review.

This skill deliberately carries no instructions. **The call is the declaration.**
It satisfies omha's route gate exactly as a written `ROUTE →` line would, and the
HUD surfaces it because Claude Code already records every `Skill` invocation in
the transcript.

Having declared the lane, continue with the work you were about to do. Do not
narrate the routing, do not restate the lane in prose, and do not call another
`route-*` skill in the same turn unless the lane genuinely changes mid-turn — in
which case call the new one, which re-declares it.

Pass your one-line reason as the skill argument so the verdict stays auditable in
the transcript without spending a line of the reply.
