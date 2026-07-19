#!/usr/bin/env python3
"""PreToolUse enforcement hook: block real-work tools until this turn declared a ROUTE.

See tests/test_route_guard.py for the contract and the verified transcript schema.
Stdlib only. Fails open on every error so a broken hook never blocks the session.
"""
import json
import os
import re
import sys
import tempfile
import time

# A fresh routing declaration: the ROUTE token followed by an arrow or colon.
# Matches `ROUTE -> x`, `ROUTE → x`, `> **ROUTE →** x`, `ROUTE: x`.
# Requires the uppercase ROUTE token + arrow/colon so prose like "the best route
# through the code" does not false-pass.
_ROUTE_RE = re.compile(r"ROUTE\s*(?:->|→|:)")


def has_route_line(text):
    """True iff `text` contains a fresh ROUTE routing declaration."""
    return bool(_ROUTE_RE.search(text))


def _is_real_user_turn(rec):
    """A genuine user message (the turn boundary) — NOT a tool_result line.

    Real user msg : type=user, content[0] is a plain string OR a {"type":"text"}
                    block, no toolUseResult.
    Tool result   : type=user, content[0].type=='tool_result', toolUseResult set.
    """
    if rec.get("type") != "user":
        return False
    if "toolUseResult" in rec:
        return False
    content = rec.get("message", {}).get("content")
    if not isinstance(content, list) or not content:
        return False
    first = content[0]
    if isinstance(first, str):  # some schema variants use a bare string block
        return True
    return first.get("type") == "text"


def _assistant_text(rec):
    """Concatenated text of an assistant message's text blocks ('' if none)."""
    if rec.get("type") != "assistant":
        return ""
    content = rec.get("message", {}).get("content")
    if not isinstance(content, list):
        return ""
    return "".join(b.get("text", "") for b in content if b.get("type") == "text")


def decide(window, sentinel_turn_id, this_turn_id):
    """Gate decision for a real-work tool call.

    allow if this turn already declared a ROUTE, OR the gate already fired this
    turn (fire-once — never nag a multi-tool turn twice); else deny.
    """
    if has_route_line(window):
        return "allow"
    if sentinel_turn_id == this_turn_id:
        return "allow"
    return "deny"


def _scan_turn(transcript_path):
    """Walk the JSONL backward; return (current-turn assistant text, boundary uuid).

    Collects assistant text from EOF back to (excluding) the most recent real user
    message; that message's uuid is the turn id. tool_result lines do NOT close the
    turn. Returns ('', None) if no real user line is found.
    """
    with open(transcript_path, encoding="utf-8") as f:
        lines = f.readlines()
    texts = []
    turn_id = None
    for ln in reversed(lines):
        ln = ln.strip()
        if not ln:
            continue
        rec = json.loads(ln)
        if _is_real_user_turn(rec):
            turn_id = rec.get("uuid")
            break
        t = _assistant_text(rec)
        if t:
            texts.append(t)
    texts.reverse()
    return "\n".join(texts), turn_id


def current_turn_window(transcript_path):
    """Assistant text emitted in the CURRENT turn ('' if none yet)."""
    return _scan_turn(transcript_path)[0]


def current_turn_id(transcript_path):
    """uuid of the user message that opened the current turn (None if none)."""
    return _scan_turn(transcript_path)[1]


# ─── sentinel I/O (fire-once per turn, keyed by session) ─────────────────────

def _sentinel_path(session_id):
    # Sanitize: session_id lands in a filename, so strip anything that could
    # traverse out of the temp dir (path separators, "..", etc.) before use.
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", session_id)
    return os.path.join(tempfile.gettempdir(), f"omha_route_gate_{safe_id}.json")


def _sentinel_read(session_id):
    try:
        with open(_sentinel_path(session_id), encoding="utf-8") as f:
            return json.load(f).get("turn_id")
    except Exception:
        return None


def _sentinel_write(session_id, turn_id):
    try:
        with open(_sentinel_path(session_id), "w", encoding="utf-8") as f:
            json.dump({"turn_id": turn_id}, f)
    except Exception:
        pass


_DENY_REASON = (
    "This turn has no ROUTE line. Per the omha cascade, re-judge this request from "
    "scratch and emit a fresh `> **ROUTE →** <lane> · <reason>` line FIRST — topic "
    "continuity is not routing continuity; do not inherit the prior turn's ROUTE by "
    "inertia. Then retry the tool call."
)


def run(stdin_obj, sentinel_read=_sentinel_read, sentinel_write=_sentinel_write,
        scan=_scan_turn, sleep=time.sleep):
    """Core gate. Returns (exit_code, stdout_dict_or_None). Fails open on any error.

    Flush-race tolerant: a real-work tool can fire before the assistant's ROUTE text
    is flushed to the transcript JSONL, so a single scan may miss a ROUTE the model
    actually emitted -> false deny. When the first (cheap, no-sleep) scan shows no
    ROUTE, re-scan up to 3 times (sleep 0.15s between attempts, ≤0.30s total) before
    concluding the turn truly has no ROUTE line.

    Latency guard: the fire-once sentinel short-circuit is checked BEFORE the
    retry-sleep loop, so on a turn already gated by an earlier tool call every
    subsequent tool call returns immediately with a single boundary scan and zero
    sleeps — the sleep is paid at most once per turn (on its first ungated tool call).
    """
    try:
        # Subagents run their own sub-conversations without the omha injection.
        if stdin_obj.get("agent_id") or stdin_obj.get("agent_type"):
            return 0, None
        transcript = stdin_obj.get("transcript_path")
        if not transcript:
            return 0, None
        # Cheap single boundary scan (no sleep). turn_id is fixed within a turn and
        # keys the sentinel; re-scans only refresh the window.
        window, turn_id = scan(transcript)
        session_id = stdin_obj.get("session_id", "")
        # Fire-once short-circuit BEFORE the sleep loop: this turn was already gated
        # by an earlier tool call, so never re-pay the retry-sleep here.
        if sentinel_read(session_id) == turn_id:
            return 0, None
        # Retry only when the first scan missed the ROUTE (possible flush lag).
        if not has_route_line(window):
            attempts = 3
            for _ in range(1, attempts):
                sleep(0.15)
                window, _ = scan(transcript)
                if has_route_line(window):
                    break
        # Mark this turn as gated so subsequent tool calls in it are not re-checked.
        # ponytail: this fires even when THIS call ends up denied (write happens
        # before the has_route_line check below) — a denied first call still
        # stamps the sentinel, so a mechanical retry of the same tool call passes
        # with no ROUTE line ever emitted. Deliberate: fire-once is keyed per-turn,
        # not per-attempt, to never nag a multi-tool turn twice (see decide()'s
        # docstring). Ceiling: a denied call is indistinguishable from a granted
        # one to later calls in the same turn. Upgrade path if this bypass is ever
        # exploited: key the sentinel per-attempt/per-tool-call instead of per-turn
        # (e.g. only mark gated on an actual allow), at the cost of re-scanning on
        # every subsequent call in a multi-tool turn.
        sentinel_write(session_id, turn_id)
        if has_route_line(window):
            return 0, None
        return 0, {"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": _DENY_REASON,
        }}
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
