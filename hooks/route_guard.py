#!/usr/bin/env python3
"""PreToolUse enforcement hook: block real-work tools until this turn declared a ROUTE.

See tests/test_route_guard.py for the contract and the verified transcript schema.
Stdlib only. Fails open on every error so a broken hook never blocks the session.
"""
import datetime as _dt
import json
import os
import re
import stat
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


# The declared VALUE, not just the token. Three things this pattern must do that
# route_log.lanes_in's does not, each from an adversarial review of the first
# version (codex, 2026-08-29):
#
#   ^…>?…    Anchor to the start of a line. The emitted form is always a line of
#            its own (`> **ROUTE →** x`), while a ROUTE written *about* routing
#            sits mid-sentence. Without the anchor, "for comparison, `ROUTE:
#            research` is invalid" made the last extracted value `research` and
#            denied a correctly-routed turn.
#   (\S+)    Capture the whole token, not `[a-z][a-z0-9-]*`. The narrow class
#            stopped at the first illegal character, so `oh-my-project/oh-my-docs`
#            (a form the cards explicitly forbid) captured a legal `oh-my-project`
#            and passed, and `ROUTE: RESEARCH` captured nothing at all — which
#            reads as "no declaration" and also passed.
#   (?=\s)   Require a trailing whitespace. A declaration sitting at the very end
#            of the scanned window may be a half-flushed line: `> **ROUTE →**
#            oh-my` would otherwise be judged as the lane `oh-my` and denied a
#            moment before it finished writing `oh-my-project`. Not matching it
#            means not judging it, which is the safe direction for this hook.
#
# The capture excludes a leading `*` on purpose. `\**` is greedy but backtracks,
# so on a half-flushed `> **ROUTE →** oh-my` it gave back one asterisk and
# captured the other one as the lane. Python 3.9 has no possessive quantifier
# (this hook targets py39), so the first character is constrained instead.
_LANE_VALUE_RE = re.compile(
    r"^[ \t]*>?[ \t]*\**ROUTE[ \t]*(?:->|→|:)\**[ \t]*([^\s*]\S*)(?=\s)", re.M)


def declared_lanes(text):
    """Every lane value declared on a line of its own, in order of declaration.

    A ROUTE mentioned inside a sentence is prose about routing, not a routing
    declaration, and is deliberately not returned."""
    return _LANE_VALUE_RE.findall(text or "")


def valid_lanes():
    """The legal ROUTE enum, read from omha's own cards.

    Returns an EMPTY set on any failure, and the caller treats empty as
    "no opinion" — an unreadable card directory must never turn the enum check
    into a gate that denies every lane. Same fail-open contract as the rest of
    this hook.

    A PARTIAL read counts as a failure, and that is the whole reason this is not
    a one-line call. `_read_cards` skips an unparseable card and keeps going —
    deliberate, so one malformed card cannot drop every other card's routing
    info. But the resulting set is missing a legal lane rather than empty, so a
    card that is merely mid-edit would make its own lane illegal and deny a
    correctly-routed turn. Only a complete read gets an opinion; the count is
    cards + 1 for handle-directly, which also refuses to trust duplicate names.
    (Named by the codex review of the first version, 2026-08-29.)"""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:      # same sibling-import shim route_stop_guard uses
            sys.path.insert(0, here)
        import route_emit
        cards = list(route_emit.CARDS_DIR.glob("*.json"))
        lanes = route_emit.lane_values(route_emit.CARDS_DIR)
        if not cards or len(lanes) != len(cards) + 1:
            return set()
        return lanes
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


def _record_diag(cwd, diag):
    """Append one gate diagnostic to `gate-diagnostics.jsonl`, best-effort.

    The retry budget below is set from a 2026-08-23 sample, and the 2026-08-31
    omo evaluation found three more denials sitting 2.8-3.5s after their ROUTE —
    all past the 1.2s budget. That is NOT enough to raise it: a transcript
    record's `timestamp` is when the model generated the message, not when the
    writer flushed it, and there is a counterexample in the same session (a
    0.43s ROUTE-to-tool gap that passed). Timing alone cannot separate "the
    writer was behind" from "the turn really had no ROUTE".

    Only the gate can, because only the gate knows what it actually saw: how
    long the window was on the first scan, whether it grew, and which of the
    three loop exits it took. So record that at every decision the retry loop
    was involved in, and set the budget from the sample later. Raising it first
    would put up to 1.2s more on every real-work tool call in every session on
    no evidence — a cost that goes everywhere to fix a denial that costs one
    round trip.

    Written beside routing.jsonl under the same opt-in-by-directory rule, so a
    project that never made the directory logs nothing. Failure is silent: this
    must never change what the gate decides.
    """
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:      # same sibling-import shim valid_lanes uses
            sys.path.insert(0, here)
        import route_log
        directory = route_log.log_dir(cwd)
        if directory is None:
            return
        # O_NOFOLLOW plus a regular-file check. A symlink planted at this path
        # and pointing at /dev/fd/1 puts diagnostic JSON on the hook's STDOUT
        # ahead of the permission envelope and corrupts the protocol — codex
        # reproduced exactly that, 2026-08-31 — and a FIFO with no reader would
        # block the hook forever. O_NONBLOCK keeps even the open from hanging.
        # O_APPEND makes each small write atomic, which is what lets several
        # hook processes share the file.
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK
        fd = os.open(os.path.join(str(directory), "gate-diagnostics.jsonl"),
                     flags, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                return
            os.write(fd, (json.dumps(diag, ensure_ascii=False) + "\n").encode("utf-8"))
        finally:
            os.close(fd)
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
        scan=_scan_turn, sleep=time.sleep, record=_record_diag):
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
        cwd = stdin_obj.get("cwd", "")
        # What the gate saw, for the budget question the timing alone cannot
        # settle. See _record_diag.
        first_chars, attempts, retry_exit = len(window), 0, "not_entered"
        turn_id_seen = turn_id
        started = time.monotonic()

        def diag(outcome, **extra):
            return {
                "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
                "outcome": outcome,
                "turn_id": turn_id,
                # The gate keys its sentinel on the FIRST scan's id; this is
                # the latest one any scan saw, so a row whose first scan hit an
                # empty transcript is still correlatable.
                "turn_id_seen": turn_id_seen,
                "session_id": session_id,
                "tool": stdin_obj.get("tool_name", ""),
                "retry_exit": retry_exit,
                "attempts_used": attempts,
                # The budget this sample was taken under. Without it a later
                # reader cannot tell numbers from an 8x0.15s gate from numbers
                # taken after somebody retuned it — which is the whole point of
                # collecting them.
                "budget_attempts": _RETRY_ATTEMPTS,
                "budget_interval_s": _RETRY_INTERVAL,
                "waited_ms": round((time.monotonic() - started) * 1000),
                "window_chars_first": first_chars,
                "window_chars_final": len(window),
                **extra,
            }

        def emit(outcome, **extra):
            # The instrument must never gate the gate. Without this the outer
            # `except Exception` below would catch a recorder failure and
            # fail-open the whole call — a logging bug would silently disable
            # enforcement, which is the expensive direction of this trade.
            try:
                record(cwd, diag(outcome, **extra))
            except Exception:
                pass

        try:
            # Retry only when the first scan missed the ROUTE (possible flush lag).
            if not has_route_line(window):
                retry_exit = "budget_exhausted"
                for _ in range(_RETRY_ATTEMPTS):
                    attempts += 1
                    prev_len = len(window)
                    sleep(_RETRY_INTERVAL)
                    window, rescan_turn_id = scan(transcript)
                    # Recorded, not adopted. The first scan's turn_id keys the
                    # sentinel and changing that would change what the gate does —
                    # this item is instrumentation. But a row whose first scan saw
                    # an empty transcript carries turn_id=null and cannot be
                    # correlated with the turn it decided (codex, 2026-08-31), so
                    # the later id is kept alongside it.
                    turn_id_seen = rescan_turn_id or turn_id_seen
                    if has_route_line(window):
                        retry_exit = "route_found"
                        break
                    # Exit early once the writer has demonstrably caught up: a
                    # NON-EMPTY window that stopped growing is a genuine negative,
                    # so spending the rest of the budget only adds latency. An empty
                    # window is not evidence of anything — the tool call proves an
                    # assistant message exists, so an empty transcript means the
                    # writer is still behind and the wait is the whole point.
                    if window and len(window) == prev_len:
                        retry_exit = "window_stalled"
                        break
        except Exception:
            # An exception inside the re-scan — a partially flushed JSONL
            # line is the obvious one — used to fail open through the outer
            # handler with NOTHING recorded, which drops exactly the
            # flush-race outcomes this sample exists to measure (codex,
            # 2026-08-31). The decision is unchanged; only the gap is.
            emit("error_fail_open")
            return 0, None
        # Below, each exit marks this turn as gated so later tool calls in it are
        # not re-checked — EXCEPT the enum deny, which deliberately does not.
        # ponytail: the no-ROUTE deny still stamps, so a mechanical retry of the
        # same tool call passes with no ROUTE line ever emitted. Deliberate:
        # fire-once is keyed per-turn, not per-attempt, to never nag a multi-tool
        # turn twice (see decide()'s docstring). Ceiling: a denied call is
        # indistinguishable from a granted one to later calls in the same turn.
        # Upgrade path if this bypass is ever exploited: key the sentinel
        # per-attempt/per-tool-call instead of per-turn, at the cost of
        # re-scanning on every subsequent call in a multi-tool turn.
        if has_route_line(window):
            # A ROUTE exists — is its VALUE a lane? Only the last declaration is
            # judged: a turn that re-routed mid-flight has corrected itself, and
            # denying it for the value it already abandoned is a false positive.
            # An empty `valid` means the cards were not read completely — no
            # opinion, allow.
            valid = valid_lanes()
            declared = declared_lanes(window)
            if valid and declared and declared[-1] not in valid:
                # Deliberately NOT stamping the fire-once sentinel on this path.
                # For a MISSING ROUTE the stamp is right — never nag a multi-tool
                # turn twice. For a WRONG lane it is not: the stamp would let an
                # unchanged retry of the same call straight through, so the deny
                # would buy one round trip of friction and no correction at all
                # (named by the codex review, 2026-08-29). Re-declaring a legal
                # lane clears it; there is no loop to get stuck in.
                emit("deny_bad_lane", declared=declared[-1])
                return 0, {"hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": _ENUM_DENY_TEMPLATE.format(
                        bad=declared[-1], valid=" | ".join(sorted(valid))),
                }}
            # The rescue is the counterfactual a denial cannot supply on its own:
            # how often the budget was needed AND sufficient. A turn whose first
            # scan already had a ROUTE writes nothing — that is the common path
            # and it would drown the interesting rows.
            if retry_exit != "not_entered":
                emit("allow_after_retry")
            sentinel_write(session_id, turn_id)
            return 0, None
        emit("deny_no_route")
        sentinel_write(session_id, turn_id)
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
