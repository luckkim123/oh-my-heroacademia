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


def test_stop_failopen_missing_transcript():
    code, out = rsg.run({"session_id": "s1"},
                        sentinel_read=lambda s: None, sentinel_write=lambda s, t: None)
    assert code == 0 and out is None


def test_stop_failopen_unreadable_transcript():
    code, out = rsg.run({"transcript_path": "/no/such.jsonl", "session_id": "s1"},
                        sentinel_read=lambda s: None, sentinel_write=lambda s, t: None)
    assert code == 0 and out is None
