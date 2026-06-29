#!/usr/bin/env python3
"""Stop backstop hook: force a ROUTE line on a pure-chat turn that skipped it.

route_guard.py gates real-work tool calls, but a turn that calls NO tool (pure
chat / self-reflection) can still skip its ROUTE line. This Stop hook catches that:
on a missing ROUTE it emits a top-level {decision:block} so the model must declare
a ROUTE before stopping. Fire-once via the shared sentinel prevents a stop-loop.

See tests/test_route_stop_guard.py. Reuses route_guard internals — no duplication.
Stdlib only; fails open on every error.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import route_guard as rg

_STOP_REASON = (
    "You finished this turn without emitting a ROUTE line. Emit "
    "`> **ROUTE →** handle-directly · <reason>` (or the correct lane) before stopping."
)


def run(stdin_obj, sentinel_read=rg._sentinel_read, sentinel_write=rg._sentinel_write):
    """Returns (exit_code, stdout_dict_or_None). Fails open on any error."""
    try:
        transcript = stdin_obj.get("transcript_path")
        if not transcript:
            return 0, None
        window, turn_id = rg._scan_turn(transcript)
        session_id = stdin_obj.get("session_id", "")
        if rg.has_route_line(window):
            return 0, None
        if sentinel_read(session_id) == turn_id:
            return 0, None  # already gated this turn — never loop the stop
        sentinel_write(session_id, turn_id)
        return 0, {"decision": "block", "reason": _STOP_REASON}
    except Exception:
        return 0, None


def main():
    try:
        stdin_obj = json.load(sys.stdin)
    except Exception:
        return 0
    code, out = run(stdin_obj)
    if out is not None:
        print(json.dumps(out))
    return code


if __name__ == "__main__":
    sys.exit(main())
