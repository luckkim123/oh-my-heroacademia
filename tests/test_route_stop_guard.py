"""Stop backstop hook: route_stop_guard.py.

Catches the pure-chat case — a turn that called NO real-work tool (so route_guard
never fired) yet still skipped its ROUTE line. On a missing ROUTE it emits a
top-level {decision:block, reason:...} forcing the model to declare a ROUTE before
stopping. Fire-once via the shared sentinel so it cannot loop forever.

Reuses route_guard's _scan_turn / has_route_line / sentinel — no duplicated logic.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))
import route_stop_guard as rsg


def _user_uuid(text, uuid):
    return {"type": "user", "uuid": uuid,
            "message": {"role": "user", "content": [{"type": "text", "text": text}]}}


def _asst_text(text):
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def _jsonl(records, tmp_path):
    p = tmp_path / "transcript.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return str(p)


def test_stop_blocks_when_turn_has_no_route(tmp_path):
    tr = _jsonl([_user_uuid("hi", "u1"), _asst_text("just chatting, no route declared")], tmp_path)
    code, out = rsg.run({"transcript_path": tr, "session_id": "s1"},
                        sentinel_read=lambda s: None, sentinel_write=lambda s, t: None)
    assert code == 0
    assert out["decision"] == "block"
    assert "ROUTE" in out["reason"]


def test_stop_allows_when_turn_has_route(tmp_path):
    tr = _jsonl([_user_uuid("hi", "u1"), _asst_text("> **ROUTE →** handle-directly · x")], tmp_path)
    code, out = rsg.run({"transcript_path": tr, "session_id": "s1"},
                        sentinel_read=lambda s: None, sentinel_write=lambda s, t: None)
    assert code == 0 and out is None


def test_stop_allows_when_already_gated_this_turn(tmp_path):
    """If route_guard already fired this turn (sentinel set), the Stop hook must not
    block again — otherwise a denied tool-call turn could loop at stop time."""
    tr = _jsonl([_user_uuid("hi", "u1"), _asst_text("no route but already gated")], tmp_path)
    code, out = rsg.run({"transcript_path": tr, "session_id": "s1"},
                        sentinel_read=lambda s: "u1", sentinel_write=lambda s, t: None)
    assert code == 0 and out is None


def test_stop_allows_when_turn_id_unresolved(tmp_path):
    """Regression: an orphan/incomplete transcript (no real user line yet, e.g. a
    subagent's own sub-transcript) resolves turn_id=None. The old code compared
    sentinel_read()==None via bare `==`, so a prior None-write matched and allowed.
    The current `_sentinel_matches_turn` requires `turn_id is not None`, so a None
    sentinel can never satisfy a None turn_id -- writing one and blocking would
    re-block on every subsequent Stop event forever. Must allow instead."""
    tr = _jsonl([_asst_text("no real user line, only assistant text")], tmp_path)
    writes = []
    code, out = rsg.run({"transcript_path": tr, "session_id": "s1"},
                        sentinel_read=lambda s: None,
                        sentinel_write=lambda s, t: writes.append(t))
    assert code == 0 and out is None
    assert writes == []  # never writes a sentinel it can't ever match later


def test_stop_failopen_missing_transcript():
    code, out = rsg.run({"session_id": "s1"},
                        sentinel_read=lambda s: None, sentinel_write=lambda s, t: None)
    assert code == 0 and out is None


def test_stop_failopen_unreadable_transcript():
    code, out = rsg.run({"transcript_path": "/no/such.jsonl", "session_id": "s1"},
                        sentinel_read=lambda s: None, sentinel_write=lambda s, t: None)
    assert code == 0 and out is None


# ─── flush-race re-scan: the Stop hook can fire before the ROUTE is flushed ───

def test_stop_reblocks_after_flush_still_no_route(tmp_path):
    """If ALL 3 re-scans still show no ROUTE (genuine pure-chat skip), block. The
    scan must be retried the full 3 times before concluding the ROUTE is absent."""
    calls = []

    def scan(_transcript):
        calls.append(1)
        return ("no route here", "u1")

    code, out = rsg.run({"transcript_path": "irrelevant", "session_id": "s1"},
                        sentinel_read=lambda s: None, sentinel_write=lambda s, t: None,
                        scan=scan, sleep=lambda s: None)
    assert code == 0
    assert out["decision"] == "block"
    assert "ROUTE" in out["reason"]
    assert len(calls) == 3  # retried the full budget before blocking


def test_stop_allows_when_route_appears_on_retry(tmp_path):
    """Core flush-race fix: the ROUTE line the model emitted lands on the 2nd scan
    (flush lag). The hook must allow and stop early — no 3rd scan."""
    calls = []

    def scan(_transcript):
        calls.append(1)
        if len(calls) == 1:
            return ("still flushing", "u1")
        return ("> **ROUTE →** handle-directly · x", "u1")

    code, out = rsg.run({"transcript_path": "irrelevant", "session_id": "s1"},
                        sentinel_read=lambda s: None, sentinel_write=lambda s, t: None,
                        scan=scan, sleep=lambda s: None)
    assert code == 0 and out is None  # allowed
    assert len(calls) == 2  # stopped early once ROUTE appeared, no 3rd scan


def test_stop_first_scan_route_no_sleep(tmp_path):
    """When the very first scan already sees the ROUTE, allow immediately: scan once,
    never sleep."""
    calls = []
    sleeps = []

    def scan(_transcript):
        calls.append(1)
        return ("> **ROUTE →** handle-directly · x", "u1")

    code, out = rsg.run({"transcript_path": "irrelevant", "session_id": "s1"},
                        sentinel_read=lambda s: None, sentinel_write=lambda s, t: None,
                        scan=scan, sleep=lambda s: sleeps.append(s))
    assert code == 0 and out is None  # allowed
    assert len(calls) == 1  # scanned exactly once
    assert sleeps == []  # never slept
