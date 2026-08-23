#!/usr/bin/env python3
"""Stop hook: append this turn's routing verdict to `.omha/routing.jsonl`.

This module used to be a blocking backstop. It caught a pure-chat turn — one that
called no tool, so route_guard (PreToolUse) never fired — that had skipped its
ROUTE line, and emitted `{decision: block}` to force the model to declare one
before stopping.

That gate is retired as of 0.9.0. Measured on this vault (25 transcripts, 206
turns): 111 turns (53.9%) called no gated tool. Those are exactly the turns where
a wrong lane costs nothing — no file is written, no agent is dispatched — and the
block's price is a full response regeneration. Enforcement now lives entirely in
route_guard, which fires the instant real work begins; a turn that drifts from
chat into work is caught at its first tool call, which is the moment that matters.

What remains is the logger, which still runs on every Stop event. It is kept HERE
rather than moved because Stop is the only event that sees a finished turn — the
lanes declared, whether the turn re-routed mid-flight, and (since 0.9.0) whether
the turn did real work at all, which is what makes `missing` interpretable.

See tests/test_route_stop_guard.py. Stdlib only; fails open on every error.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import route_guard as rg
import route_log


def log_turn(stdin_obj, scan=rg._scan_turn, writer=route_log.record):
    """Append this turn's verdict to `.omha/routing.jsonl` (no-op when off).

    A turn that skipped its ROUTE line is still the most interesting record in
    the file, so it is logged too — paired with `work`, which says whether the
    silence was correct (a chat turn) or a genuine miss (a work turn).

    Uses its own scan rather than sharing one with the gate, so a logging change
    can never perturb route_guard's decision."""
    try:
        transcript = stdin_obj.get("transcript_path")
        if not transcript:
            return None
        window, turn_id = scan(transcript)
        if turn_id is None:
            return None  # no resolvable turn (orphan/subagent transcript)
        prompt = route_log.turn_prompt(transcript, rg._is_real_user_turn)
        work = route_log.turn_used_real_work(transcript, rg._is_real_user_turn)
        return writer(stdin_obj.get("cwd"), turn_id, window, prompt,
                      session_id=stdin_obj.get("session_id", ""), work=work)
    except Exception:
        return None  # a logger must never break the session


def main():
    try:
        stdin_obj = json.load(sys.stdin)
    except Exception:
        return 0
    log_turn(stdin_obj)
    return 0


if __name__ == "__main__":
    sys.exit(main())
