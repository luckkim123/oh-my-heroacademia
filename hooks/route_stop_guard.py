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
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import route_guard as rg

_STOP_REASON = (
    "You finished this turn without emitting a ROUTE line. Emit "
    "`> **ROUTE →** handle-directly · <reason>` (or the correct lane) before stopping."
)


def run(stdin_obj, sentinel_read=rg._sentinel_read, sentinel_write=rg._sentinel_write,
        scan=rg._scan_turn, sleep=time.sleep):
    """Returns (exit_code, stdout_dict_or_None). Fails open on any error.

    Flush-race tolerant: the Stop hook can fire before the assistant's text block is
    flushed to the transcript JSONL, so a single scan may miss a ROUTE line the model
    actually emitted. Re-scan up to 3 times (sleep 0.15s between attempts, ≤0.30s
    total) before concluding the turn truly has no ROUTE line.
    """
    try:
        transcript = stdin_obj.get("transcript_path")
        if not transcript:
            return 0, None
        session_id = stdin_obj.get("session_id", "")
        turn_id = None
        attempts = 3
        for i in range(attempts):
            window, scanned_turn_id = scan(transcript)
            if i == 0:
                # Turn boundary is fixed within a turn; pin it from the first scan.
                turn_id = scanned_turn_id
            if rg.has_route_line(window):
                return 0, None  # ROUTE present (possibly after flush) — allow
            if i < attempts - 1:
                sleep(0.15)
        # All attempts exhausted with no ROUTE line — existing sentinel logic.
        if rg._sentinel_matches_turn(sentinel_read(session_id), turn_id):
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
