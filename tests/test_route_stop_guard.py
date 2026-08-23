"""Stop hook: route_stop_guard.py — logging only, since 0.9.0.

The blocking backstop is retired. It existed to catch a pure-chat turn that
skipped its ROUTE line, but pure-chat turns are exactly the turns where routing
costs nothing to get wrong: no file is touched, no agent is dispatched. What is
left is `log_turn`, which still appends every turn's verdict to routing.jsonl —
so this module is now a logger that happens to run on the Stop event.

Enforcement lives entirely in route_guard (PreToolUse), which fires the instant
real work begins. See tests/test_route_guard.py.
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


def _run_main(stdin_obj, monkeypatch, capsys):
    """Drive main() end to end; return whatever it wrote to stdout."""
    import io
    monkeypatch.setattr(rsg.sys, "stdin", io.StringIO(json.dumps(stdin_obj)))
    assert rsg.main() == 0
    return capsys.readouterr().out


def test_stop_emits_nothing_for_a_chat_turn_without_a_route(tmp_path, monkeypatch, capsys):
    """The retired behaviour. A tool-less turn is free to skip its ROUTE line;
    a `{decision: block}` on stdout is what used to force the rewrite."""
    tr = _jsonl([_user_uuid("hi", "u1"), _asst_text("just chatting, no route declared")], tmp_path)
    assert _run_main({"transcript_path": tr, "session_id": "s1", "cwd": str(tmp_path)},
                     monkeypatch, capsys) == ""


def test_stop_emits_nothing_when_a_route_is_present(tmp_path, monkeypatch, capsys):
    tr = _jsonl([_user_uuid("hi", "u1"), _asst_text("> **ROUTE →** handle-directly · x")], tmp_path)
    assert _run_main({"transcript_path": tr, "session_id": "s1", "cwd": str(tmp_path)},
                     monkeypatch, capsys) == ""


def test_the_blocking_gate_is_gone(tmp_path):
    """No `run()` and no block reason may survive — a leftover would re-block chat turns."""
    assert not hasattr(rsg, "run")
    assert not hasattr(rsg, "_STOP_REASON")


def test_logging_still_runs_on_the_stop_event(tmp_path):
    (tmp_path / ".omha").mkdir()
    tr = _jsonl([_user_uuid("hi", "u1"), _asst_text("> **ROUTE →** superpowers · x")], tmp_path)
    rsg.log_turn({"transcript_path": tr, "cwd": str(tmp_path), "session_id": "s1"})
    rec = json.loads((tmp_path / ".omha" / "routing.jsonl").read_text().strip())
    assert rec["lanes"] == ["superpowers"]


def test_stop_failopen_missing_transcript(monkeypatch, capsys):
    assert _run_main({}, monkeypatch, capsys) == ""


def test_stop_failopen_unreadable_transcript(monkeypatch, capsys):
    assert _run_main({"transcript_path": "/nonexistent/x.jsonl", "session_id": "s"},
                     monkeypatch, capsys) == ""
