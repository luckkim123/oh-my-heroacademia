"""PreToolUse enforcement hook: route_guard.py.

Deterministic gate that blocks Bash/Agent/Task/Edit/Write unless the CURRENT turn
already emitted a fresh `ROUTE ->` line. Closes the "skipped the re-route check by
inertia" failure that passive reminders (card + memory) provably cannot enforce
(Compliance-Gap theorem, arXiv 2605.01771).

Design (see workflow synthesis 2026-06-29):
  - has_route_line   — pure: does turn text contain a fresh ROUTE marker?
  - current_turn_window — pure: transcript lines -> this turn's assistant text
  - decide           — pure: (window, sentinel_turn_id, this_turn_id) -> allow|deny
  - e2e              — stdin JSON -> stdout permissionDecision envelope
  - fail-open        — bad json / missing transcript / subagent -> allow

Transcript schema (verified empirically against a real session transcript):
  real user turn  : {"type":"user","message":{"role":"user","content":[{"type":"text",...}]}}  (toolUseResult absent)
  tool result     : {"type":"user","message":{"role":"user","content":[{"type":"tool_result",...}]},"toolUseResult":...}
  assistant text  : {"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":...}]}}
  assistant tool  : {"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use",...}]}}
  meta lines      : type in {attachment,last-prompt,ai-title,mode,queue-operation} -> ignored
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))
import route_guard as rg

# ─── group 1: has_route_line — fresh ROUTE marker detection ──────────────────

def test_plain_arrow_route_detected():
    assert rg.has_route_line("ROUTE -> oh-my-claudecode · reason") is True


def test_unicode_arrow_route_detected():
    assert rg.has_route_line("ROUTE → handle-directly · reason") is True


def test_gfm_blockquote_route_detected():
    assert rg.has_route_line("> **ROUTE →** oh-my-claudecode · reason") is True


def test_colon_form_route_detected():
    """STAGE lines and some phrasings use `ROUTE:` — still a routing declaration."""
    assert rg.has_route_line("ROUTE: handle-directly") is True


def test_no_route_returns_false():
    assert rg.has_route_line("Sure, let me look at that file for you.") is False


def test_word_route_in_prose_not_matched():
    """The bare word 'route' in prose is not a routing declaration — require the
    ROUTE token followed by an arrow/colon so prose mentions don't false-pass."""
    assert rg.has_route_line("I'll find the best route through the codebase.") is False


# ─── group 2: current_turn_window — transcript -> this turn's assistant text ──
#
# Real transcript line shapes (verified empirically):
#   user msg : {"type":"user","message":{"role":"user","content":[{"type":"text","text":...}]}}
#   tool res : {"type":"user","message":{"role":"user","content":[{"type":"tool_result",...}]},"toolUseResult":{...}}
#   asst text: {"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":...}]}}
#   asst tool: {"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use",...}]}}
#   meta     : {"type":"attachment"} / "last-prompt" / "ai-title" / "mode" / "queue-operation"

def _user(text):
    return {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": text}]}}


def _tool_result(out):
    return {"type": "user", "toolUseResult": {"x": 1},
            "message": {"role": "user", "content": [{"type": "tool_result", "content": out}]}}


def _asst_text(text):
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def _asst_tool(name):
    return {"type": "assistant",
            "message": {"role": "assistant", "content": [{"type": "tool_use", "name": name, "input": {}}]}}


def _jsonl(records, tmp_path):
    p = tmp_path / "transcript.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return str(p)


def test_window_collects_current_turn_assistant_text(tmp_path):
    """Window = assistant text from EOF back to (excluding) the last real user msg."""
    tr = _jsonl([
        _user("old question"),
        _asst_text("> **ROUTE →** handle-directly · old"),
        _user("do the real work now"),
        _asst_text("> **ROUTE →** oh-my-claudecode · this"),
        _asst_tool("Bash"),
    ], tmp_path)
    win = rg.current_turn_window(tr)
    assert "oh-my-claudecode · this" in win
    assert "handle-directly · old" not in win  # stale prior-turn ROUTE must NOT leak


def test_window_stops_at_real_user_not_tool_result(tmp_path):
    """A tool_result line is type=user but is NOT a turn boundary — the window must
    span across it back to the real user message."""
    tr = _jsonl([
        _user("real user message with ROUTE coming"),
        _asst_text("> **ROUTE →** oh-my-claudecode · r"),
        _asst_tool("Bash"),
        _tool_result("command output"),
        _asst_text("now continuing after the tool result"),
        _asst_tool("Edit"),
    ], tmp_path)
    win = rg.current_turn_window(tr)
    assert "oh-my-claudecode · r" in win          # ROUTE before the tool_result is in-window
    assert "now continuing" in win                # text after tool_result also in-window


def test_window_empty_when_no_assistant_text_yet(tmp_path):
    """First tool call of a turn with no preceding assistant text -> empty window."""
    tr = _jsonl([
        _user("just asked"),
        _asst_tool("Bash"),
    ], tmp_path)
    assert rg.current_turn_window(tr) == ""


def test_window_ignores_meta_lines(tmp_path):
    tr = _jsonl([
        _user("q"),
        {"type": "attachment"},
        _asst_text("> **ROUTE →** handle-directly · a"),
        {"type": "mode"},
    ], tmp_path)
    assert "handle-directly · a" in rg.current_turn_window(tr)


# ─── group 3: decide — fire-once sentinel gate ───────────────────────────────
#
# decide(window, sentinel_turn_id, this_turn_id) -> "allow" | "deny"
#   - window has ROUTE                          -> allow
#   - sentinel already gated THIS turn          -> allow (fire-once: never nag twice)
#   - window lacks ROUTE and turn not yet gated -> deny

def test_decide_allows_when_route_present():
    assert rg.decide("> **ROUTE →** omc · x", sentinel_turn_id=None, this_turn_id="t1") == "allow"


def test_decide_denies_when_no_route_and_fresh_turn():
    assert rg.decide("just some text", sentinel_turn_id=None, this_turn_id="t1") == "deny"


def test_decide_allows_when_sentinel_already_gated_this_turn():
    """Fire-once: once a turn has been denied (sentinel written), later tool calls
    in the SAME turn pass — the model is interrupted exactly once."""
    assert rg.decide("still no route", sentinel_turn_id="t1", this_turn_id="t1") == "allow"


def test_decide_denies_when_sentinel_is_from_a_different_turn():
    """A stale sentinel from a prior turn must NOT suppress this turn's gate."""
    assert rg.decide("no route here", sentinel_turn_id="t0", this_turn_id="t1") == "deny"


# ─── group 4: current_turn_id — boundary user-line uuid keys the sentinel ─────

def _user_uuid(text, uuid):
    r = _user(text)
    r["uuid"] = uuid
    return r


def test_turn_id_is_boundary_user_uuid(tmp_path):
    tr = _jsonl([
        _user_uuid("first", "uuid-0"),
        _asst_text("> **ROUTE →** x · 1"),
        _user_uuid("second real turn", "uuid-1"),
        _asst_text("working"),
        _asst_tool("Bash"),
    ], tmp_path)
    assert rg.current_turn_id(tr) == "uuid-1"


def test_turn_id_none_when_no_user_line(tmp_path):
    tr = _jsonl([_asst_text("orphan")], tmp_path)
    assert rg.current_turn_id(tr) is None


# ─── group 5: run() e2e — stdin dict -> (exit_code, stdout_obj) ───────────────
#
# run(stdin_obj, sentinel_read, sentinel_write) returns (exit, out_dict_or_None).
# Injecting sentinel read/write keeps the e2e test pure (no real /tmp file).

def test_e2e_allow_when_route_present(tmp_path):
    tr = _jsonl([_user_uuid("go", "u1"), _asst_text("> **ROUTE →** omc · x"), _asst_tool("Bash")], tmp_path)
    code, out = rg.run({"transcript_path": tr, "tool_name": "Bash", "session_id": "s1"},
                       sentinel_read=lambda s: None, sentinel_write=lambda s, t: None)
    assert code == 0 and out is None


def test_e2e_deny_when_no_route(tmp_path):
    tr = _jsonl([_user_uuid("go", "u1"), _asst_tool("Bash")], tmp_path)
    code, out = rg.run({"transcript_path": tr, "tool_name": "Bash", "session_id": "s1"},
                       sentinel_read=lambda s: None, sentinel_write=lambda s, t: None)
    assert code == 0
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "ROUTE" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_e2e_fire_once_second_call_allows(tmp_path):
    """Sentinel written on first deny; second call same turn reads it -> allow."""
    tr = _jsonl([_user_uuid("go", "u1"), _asst_tool("Edit")], tmp_path)
    store = {}
    code1, out1 = rg.run({"transcript_path": tr, "tool_name": "Edit", "session_id": "s1"},
                         sentinel_read=lambda s: store.get(s), sentinel_write=lambda s, t: store.__setitem__(s, t))
    code2, out2 = rg.run({"transcript_path": tr, "tool_name": "Edit", "session_id": "s1"},
                         sentinel_read=lambda s: store.get(s), sentinel_write=lambda s, t: store.__setitem__(s, t))
    assert out1["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert out2 is None  # fire-once: second call in same turn allowed


# ─── group 6: fail-open — never block on error/subagent ──────────────────────

def test_failopen_subagent(tmp_path):
    tr = _jsonl([_user_uuid("go", "u1"), _asst_tool("Bash")], tmp_path)
    code, out = rg.run({"transcript_path": tr, "tool_name": "Bash", "session_id": "s1", "agent_id": "sub1"},
                       sentinel_read=lambda s: None, sentinel_write=lambda s, t: None)
    assert code == 0 and out is None


def test_failopen_missing_transcript_path():
    code, out = rg.run({"tool_name": "Bash", "session_id": "s1"},
                       sentinel_read=lambda s: None, sentinel_write=lambda s, t: None)
    assert code == 0 and out is None


def test_failopen_unreadable_transcript():
    code, out = rg.run({"transcript_path": "/no/such/file.jsonl", "tool_name": "Bash", "session_id": "s1"},
                       sentinel_read=lambda s: None, sentinel_write=lambda s, t: None)
    assert code == 0 and out is None


def test_failopen_malformed_jsonl_line(tmp_path):
    """A corrupt line in the transcript must degrade to allow, never hard-block."""
    p = tmp_path / "t.jsonl"
    p.write_text(json.dumps(_user("go")) + "\n{ this is not json }\n")
    code, out = rg.run({"transcript_path": str(p), "tool_name": "Bash", "session_id": "s1"},
                       sentinel_read=lambda s: None, sentinel_write=lambda s, t: None)
    assert code == 0 and out is None


# ─── group 7: run() flush-race — sentinel-gated re-scan before deny ───────────
#
# The Stop-hook flush-race (route_stop_guard) also affects the PreToolUse gate: a
# real-work tool can fire before the ROUTE text is flushed to the JSONL, so a
# single scan may miss a ROUTE the model actually emitted -> false deny. run()
# re-scans up to 3 times (sleep 0.15s between) before concluding no ROUTE. The
# sentinel short-circuit MUST precede the sleep loop so a fire-once (already-gated)
# turn never re-pays the sleep on every subsequent tool call — that is the latency
# bug a naive port of the Stop-hook loop introduces.
#
# run(stdin_obj, sentinel_read, sentinel_write, scan=_scan_turn, sleep=time.sleep)


def test_run_allows_when_route_appears_on_retry(tmp_path):
    """ROUTE lands on the 2nd scan (flush lag) -> allow, scan twice (no 3rd), sleep once."""
    calls = []
    sleeps = []

    def scan(_transcript):
        calls.append(1)
        if len(calls) == 1:
            return ("still flushing", "u1")
        return ("> **ROUTE →** oh-my-claudecode · x", "u1")

    code, out = rg.run({"transcript_path": "irrelevant", "tool_name": "Bash", "session_id": "s1"},
                       sentinel_read=lambda s: None, sentinel_write=lambda s, t: None,
                       scan=scan, sleep=lambda s: sleeps.append(s))
    assert code == 0 and out is None          # allowed
    assert len(calls) == 2                     # stopped early once ROUTE appeared
    assert len(sleeps) == 1                    # slept exactly once (between scan 1 and 2)


def test_run_denies_after_full_retry_still_no_route(tmp_path):
    """All 3 scans still show no ROUTE (genuine skip) -> deny, scan 3x, sleep 2x."""
    calls = []
    sleeps = []

    def scan(_transcript):
        calls.append(1)
        return ("no route here", "u1")

    code, out = rg.run({"transcript_path": "irrelevant", "tool_name": "Bash", "session_id": "s1"},
                       sentinel_read=lambda s: None, sentinel_write=lambda s, t: None,
                       scan=scan, sleep=lambda s: sleeps.append(s))
    assert code == 0
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert len(calls) == 3                     # retried the full budget before deny
    assert len(sleeps) == 2                    # slept between each of the 3 scans


def test_run_first_scan_route_no_sleep(tmp_path):
    """First scan already sees ROUTE -> allow immediately: scan once, never sleep."""
    calls = []
    sleeps = []

    def scan(_transcript):
        calls.append(1)
        return ("> **ROUTE →** oh-my-claudecode · x", "u1")

    code, out = rg.run({"transcript_path": "irrelevant", "tool_name": "Bash", "session_id": "s1"},
                       sentinel_read=lambda s: None, sentinel_write=lambda s, t: None,
                       scan=scan, sleep=lambda s: sleeps.append(s))
    assert code == 0 and out is None          # allowed
    assert len(calls) == 1                     # scanned exactly once
    assert sleeps == []                        # never slept


# ─── group 8: real sentinel + unresolved turn_id — None==None bypass ─────────
#
# Regression for the sentinel bypass: when turn_id can't be resolved (no real
# user line recognized in the transcript) AND no sentinel file exists yet for
# the session (real _sentinel_read returns None on FileNotFoundError), a bare
# `sentinel_read(session_id) == turn_id` comparison is None == None -> True,
# short-circuiting to allow with the ROUTE check never reached.

def test_e2e_unresolved_turn_id_and_no_sentinel_denies(tmp_path):
    """Orphan transcript (assistant text only, no real user line) -> turn_id is
    None. A fresh session has no sentinel file yet -> real _sentinel_read also
    returns None. These two Nones must NOT be treated as a sentinel match; the
    call must fall through to the ROUTE check and deny (zero ROUTE emitted)."""
    tr = _jsonl([_asst_text("just chatting, no user boundary, no route")], tmp_path)
    session_id = f"test-no-bypass-{tmp_path.name}"
    sentinel_file = Path(rg._sentinel_path(session_id))
    if sentinel_file.exists():
        sentinel_file.unlink()
    try:
        code, out = rg.run({"transcript_path": tr, "tool_name": "Bash", "session_id": session_id})
        assert code == 0
        assert out is not None, "sentinel None==None bypass: tool call allowed with no ROUTE line"
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    finally:
        if sentinel_file.exists():
            sentinel_file.unlink()


def test_run_sentinel_short_circuits_before_sleep(tmp_path):
    """★ latency-bug guard: the sentinel already gated THIS turn (fire-once from an
    earlier tool call) and the window has NO ROUTE. run() must allow immediately via
    the sentinel short-circuit — one boundary scan, ZERO sleeps — never re-paying the
    retry-sleep loop on every subsequent tool call of a denied turn."""
    calls = []
    sleeps = []

    def scan(_transcript):
        calls.append(1)
        return ("no route in window", "u1")

    code, out = rg.run({"transcript_path": "irrelevant", "tool_name": "Bash", "session_id": "s1"},
                       sentinel_read=lambda s: "u1",  # already gated this turn
                       sentinel_write=lambda s, t: None,
                       scan=scan, sleep=lambda s: sleeps.append(s))
    assert code == 0 and out is None          # allowed via fire-once short-circuit
    assert len(calls) == 1                     # only the cheap boundary scan
    assert sleeps == []                        # short-circuit BEFORE any sleep


# ─── group 8: _sentinel_path — session_id sanitized before filename build ─────

def test_sentinel_path_strips_path_traversal():
    """session_id containing '../' must not escape the temp dir."""
    path = rg._sentinel_path("../../etc/passwd")
    assert os.path.dirname(path) == tempfile.gettempdir()
    assert ".." not in os.path.basename(path)
    assert "/" not in os.path.basename(path)


def test_sentinel_path_strips_absolute_path_injection():
    """A session_id that looks like an absolute path is neutralized too."""
    path = rg._sentinel_path("/etc/passwd")
    assert os.path.dirname(path) == tempfile.gettempdir()


def test_sentinel_path_normal_id_unchanged():
    """Ordinary alphanumeric/uuid-style session_id passes through untouched."""
    path = rg._sentinel_path("abc123-DEF_456")
    assert os.path.basename(path) == "omha_route_gate_abc123-DEF_456.json"
