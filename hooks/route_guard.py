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


# The declared VALUE, not just the token. route_log.lanes_in's regex, verbatim —
# it already survives every emitted form (`> **ROUTE →** x`, `ROUTE: x`).
_LANE_VALUE_RE = re.compile(r"ROUTE\s*(?:->|→|:)\**\s*([a-z][a-z0-9-]*)")


def declared_lanes(text):
    """Every lane value declared in this turn, in order of declaration."""
    return _LANE_VALUE_RE.findall(text or "")


def valid_lanes():
    """The legal ROUTE enum, read from omha's own cards.

    Returns an EMPTY set on any failure, and the caller treats empty as
    "no opinion" — an unreadable card directory must never turn the enum check
    into a gate that denies every lane. Same fail-open contract as the rest of
    this hook."""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:      # same sibling-import shim route_stop_guard uses
            sys.path.insert(0, here)
        import route_emit
        return route_emit.lane_values(route_emit.CARDS_DIR)
    except Exception:
        return set()


# Injected user-role records that are NOT the user asking for anything. Claude
# Code delivers a peer session's message, and the notice that one was delivered,
# as type=user with string content — structurally identical to a typed prompt.
# Measured on this vault 2026-08-23: of 1,171 user-role records, 125 were these.
# Treating one as a turn boundary discards the ROUTE the model already emitted
# for the real prompt, so every later tool call in that turn is denied over a
# routing declaration that exists. Confirmed as the cause of one denial in a
# live session (boundary "[Cross-session delivery notice] …", window 111 chars
# with no ROUTE, while the turn's actual ROUTE sat just outside it).
#
# Narrow on purpose. `/compact` and other local-command records stay boundaries:
# a pre-compact ROUTE must NOT satisfy the gate afterwards, and one denial in
# the same session (window 0 chars right after /compact) was correct. These two
# prefixes are the only user-role records carrying no user request at all, so
# excluding them cannot be used to skip a routing decision — a peer session can
# report work, never ask for it.
#
# The price, stated plainly because it is real: the window grows. Replaying the
# same session after this change, turns that had been chopped into fragments by
# peer traffic re-merged into one 15,254-char window, and a single ROUTE at the
# top covers all of it. That is the correct semantics — routing is decided per
# USER request, and no user request happened in between — but it does mean a
# long peer-heavy turn is gated by one declaration. If a peer ever needs to
# force a re-route, the fix is for the model to emit a fresh ROUTE, not for the
# transport to fake a turn boundary.
_SYNTHETIC_USER_PREFIXES = (
    "[Cross-session delivery notice]",
    "Another Claude session sent a message",
)


def _is_synthetic_user_record(content):
    """True for a user-role record that is an injected notice, not a prompt."""
    return isinstance(content, str) and content.startswith(_SYNTHETIC_USER_PREFIXES)


def _is_real_user_turn(rec):
    """A genuine user message (the turn boundary) — NOT a tool_result line.

    Real user msg : type=user, no toolUseResult, and content is either a bare
                    string, or a list whose first block is a string or
                    {"type":"text"}.
    Tool result   : type=user, content[0].type=='tool_result', toolUseResult set.

    The bare-string form is not a variant to be tolerant about — it is what a
    typed prompt actually looks like. Measured on one live transcript: 4 real
    prompts, all `content` as a plain string; 146 tool results, all list-form
    with toolUseResult. Requiring a list therefore found NO turn boundary in the
    whole session, and a None turn_id makes route_stop_guard allow every stop and
    leaves _scan_turn's window spanning the entire transcript — where some older
    turn's ROUTE line always matches, so route_guard allows every tool call too.
    Both gates were silently open on this schema.
    """
    if rec.get("type") != "user":
        return False
    if "toolUseResult" in rec:
        return False
    content = rec.get("message", {}).get("content")
    if _is_synthetic_user_record(content):
        return False
    if isinstance(content, str):
        return bool(content)
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


def _sentinel_matches_turn(sentinel_turn_id, turn_id):
    """True iff the fire-once sentinel already gated THIS specific turn.

    turn_id is None when the transcript has no resolvable turn boundary (e.g.
    an orphan/incomplete transcript with no real user line yet). In that case
    there is no genuine turn to match against, so a None sentinel must never
    be treated as matching a None turn_id via bare ==. That coincidence used
    to let a real-work tool call through with zero ROUTE line ever checked —
    the sentinel bypass. Shared by route_guard.run(), route_stop_guard.run(),
    and decide() so the guard can't drift out of sync between callers.
    """
    return turn_id is not None and sentinel_turn_id == turn_id


def decide(window, sentinel_turn_id, this_turn_id):
    """Gate decision for a real-work tool call.

    allow if this turn already declared a ROUTE, OR the gate already fired this
    turn (fire-once — never nag a multi-tool turn twice); else deny.
    """
    if has_route_line(window):
        return "allow"
    if _sentinel_matches_turn(sentinel_turn_id, this_turn_id):
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


# Flush-race budget. A real-work tool can fire before the assistant's ROUTE text
# reaches the transcript JSONL, and 3 x 0.15s (0.30s) was not enough. Measured
# 2026-08-23 by replaying _scan_turn against a live session's transcript at each
# of its 9 denials: 7 had a ROUTE in the window after the fact — the declaration
# was real, the hook simply read the file before it landed. A denied call costs a
# full model round trip, so trading up to ~1.2s of hook latency for it is heavily
# positive, and the loop rarely spends it (see run()).
_RETRY_ATTEMPTS = 8
_RETRY_INTERVAL = 0.15

_DENY_REASON = (
    "This turn has no ROUTE line. Per the omha cascade, re-judge this request from "
    "scratch and emit a fresh `> **ROUTE →** <lane> · <reason>` line FIRST — topic "
    "continuity is not routing continuity; do not inherit the prior turn's ROUTE by "
    "inertia. Then retry the tool call."
)

# Enum resistance. Measured on this vault 2026-08-29: 15 of 788 logged records
# named a value outside the card set and nothing anywhere pushed back, so the
# log — the only evidence any card change is argued from — was quietly polluted.
# Twelve came from teammate turns naming an OMC *agent* (`research`, `code`,
# `explore`, `execute`, `debug`); three named `oh-my-orchestrator`, a plugin
# that is deliberately not a lane. Rare by construction (1.9%), so this denies
# almost never — a detector that fires on everything detects nothing.
_ENUM_DENY_TEMPLATE = (
    "This turn's ROUTE names `{bad}`, which is not a lane. The value must be exactly "
    "one of: {valid}. An agent name, a skill name or a plugin name is not a lane — "
    "`research`/`code`/`explore`/`execute`/`debug` are OMC agents, and "
    "`oh-my-orchestrator` is a harness, not a routing destination. Re-judge with the "
    "omha cascade, emit a fresh `> **ROUTE →** <lane> · <reason>` line carrying a "
    "legal value, then retry the tool call."
)


def run(stdin_obj, sentinel_read=_sentinel_read, sentinel_write=_sentinel_write,
        scan=_scan_turn, sleep=time.sleep):
    """Core gate. Returns (exit_code, stdout_dict_or_None). Fails open on any error.

    Flush-race tolerant: a real-work tool can fire before the assistant's ROUTE text
    is flushed to the transcript JSONL, so a single scan may miss a ROUTE the model
    actually emitted -> false deny. When the first (cheap, no-sleep) scan shows no
    ROUTE, re-scan up to _RETRY_ATTEMPTS times (_RETRY_INTERVAL apart, ≤1.2s total)
    before concluding the turn truly has no ROUTE line.

    The budget is rarely spent. The loop stops the moment a ROUTE appears, and also
    the moment a NON-EMPTY window stops growing — the writer has caught up, so the
    turn genuinely has no ROUTE and further waiting buys nothing. Only a transcript
    still empty for this turn runs to the cap, and that is exactly the case where
    the wait is warranted: the tool call itself proves an assistant message exists,
    so an empty window means the writer is behind, not that the model said nothing.

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
        if _sentinel_matches_turn(sentinel_read(session_id), turn_id):
            return 0, None
        # Retry only when the first scan missed the ROUTE (possible flush lag).
        if not has_route_line(window):
            for _ in range(_RETRY_ATTEMPTS):
                prev_len = len(window)
                sleep(_RETRY_INTERVAL)
                window, _ = scan(transcript)
                if has_route_line(window):
                    break
                # Exit early once the writer has demonstrably caught up: a
                # NON-EMPTY window that stopped growing is a genuine negative,
                # so spending the rest of the budget only adds latency. An empty
                # window is not evidence of anything — the tool call proves an
                # assistant message exists, so an empty transcript means the
                # writer is still behind and the wait is the whole point.
                if window and len(window) == prev_len:
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
            # A ROUTE exists — is its VALUE a lane? Only the last declaration is
            # judged: a turn that re-routed mid-flight has corrected itself, and
            # denying it for the value it already abandoned is a false positive.
            # An empty `valid` means the cards were unreadable — no opinion, allow.
            valid = valid_lanes()
            declared = declared_lanes(window)
            if valid and declared and declared[-1] not in valid:
                return 0, {"hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": _ENUM_DENY_TEMPLATE.format(
                        bad=declared[-1], valid=" | ".join(sorted(valid))),
                }}
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
