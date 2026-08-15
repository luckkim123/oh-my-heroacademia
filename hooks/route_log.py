#!/usr/bin/env python3
"""Append one record per turn to `.omha/routing.jsonl` — what was routed where.

Why this exists: every card edit so far has been argued from an anecdote ("this
session repeatedly got X wrong"). Anecdotes are how the block grew to 15,714
chars. A verdict log turns "the card needs another gate" into a question the
data can answer — which requests get mis-routed, which lanes get re-routed
mid-turn, whether ANALYZE fires when it should.

Opt-in by directory: writes only when `.omha/` already exists in the session's
cwd. A plugin hook runs in every repository the operator opens, and silently
creating a dot-dir in each of them is not something a routing plugin should do.
`mkdir .omha` turns it on for that project.

Append-only, one line per Stop event. The Stop gate can fire twice on a turn
that had to be sent back for its ROUTE line, so records are NOT unique per
turn_id — group by turn_id and take the last when reading.

Stdlib only. Every failure is swallowed: a logger must never break a session.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

# `> **ROUTE →** oh-my-project · reason` / `ROUTE: handle-directly` / `ROUTE -> omc`
_LANE_RE = re.compile(r"ROUTE\s*(?:->|→|:)\**\s*([a-z][a-z0-9-]*)")
PROMPT_EXCERPT = 160


def lanes_in(text):
    """Every lane declared in this turn's assistant text, in order.

    Two or more means the turn re-routed mid-flight — the behaviour the
    re-routing gates ask for, and the thing worth counting."""
    return _LANE_RE.findall(text or "")


def _user_text(rec):
    """Text of a real user message ('' if none)."""
    content = rec.get("message", {}).get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for b in content:
        if isinstance(b, str):
            parts.append(b)
        elif isinstance(b, dict) and b.get("type") == "text":
            parts.append(b.get("text", ""))
    return "".join(parts)


def turn_prompt(transcript_path, is_real_user_turn):
    """First PROMPT_EXCERPT chars of the prompt that opened the current turn.

    Takes the predicate as an argument rather than importing route_guard, so the
    logger stays a leaf module (route_stop_guard already owns that import)."""
    try:
        with open(transcript_path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return ""
    for ln in reversed(lines):
        ln = ln.strip()
        if not ln:
            continue
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if is_real_user_turn(rec):
            return " ".join(_user_text(rec).split())[:PROMPT_EXCERPT]
    return ""


def log_dir(cwd):
    """The `.omha/` directory for this session, or None when logging is off.

    No `os.getcwd()` fallback on purpose. A hook's process cwd is not the
    session's cwd, and guessing wrote a log into the plugin's own repo during
    development. Absent cwd means off, not somewhere-else."""
    if not cwd:
        return None
    try:
        d = Path(cwd) / ".omha"
    except (TypeError, ValueError):
        return None
    return d if d.is_dir() else None


def build_record(turn_id, window, prompt, now=None, session_id=""):
    """One record. `session_id` is the join key to ~/.claude/metrics/usage.jsonl.

    Without it the two logs can still be joined — turn_id IS the transcript
    record's uuid — but only by scanning every transcript in the project, which
    is what makes "cost per lane" expensive rather than impossible. Recording it
    here turns that scan into a dict lookup. Defaults to "" so the field is
    always present and old readers keep working."""
    lanes = lanes_in(window)
    return {
        "ts": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        "turn_id": turn_id,
        "session_id": session_id,
        "lanes": lanes,
        "rerouted": len(lanes) > 1,
        "missing": not lanes,
        "analyze": "ANALYZE" in (window or ""),
        "prompt": prompt,
    }


def record(cwd, turn_id, window, prompt, now=None, session_id=""):
    """Append one record. Returns the path written, or None when off/failed."""
    d = log_dir(cwd)
    if d is None:
        return None
    path = d / "routing.jsonl"
    try:
        line = json.dumps(build_record(turn_id, window, prompt, now, session_id),
                          ensure_ascii=False)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        return path
    except (OSError, TypeError, ValueError):
        return None


# ─── reading it back ─────────────────────────────────────────────────────────

def load(path):
    """Records from a routing.jsonl, deduped to the LAST record per turn.

    The Stop gate fires twice on a turn it had to send back for its ROUTE line,
    which writes a `missing` record and then a corrected one. Counting both would
    report a miss rate roughly double the real one."""
    latest = {}
    try:
        with open(path, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rec = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                latest[rec.get("turn_id")] = rec
    except OSError:
        return []
    return list(latest.values())


def summarize(records):
    """Counts worth acting on: lane distribution, misses, re-routes, ANALYZE."""
    lanes = {}
    for r in records:
        for lane in r.get("lanes", []):
            lanes[lane] = lanes.get(lane, 0) + 1
    return {
        "turns": len(records),
        "missing": sum(1 for r in records if r.get("missing")),
        "rerouted": sum(1 for r in records if r.get("rerouted")),
        "analyze": sum(1 for r in records if r.get("analyze")),
        "lanes": dict(sorted(lanes.items(), key=lambda kv: -kv[1])),
    }


def _cli(argv):
    root = argv[1] if len(argv) > 1 else "."
    path = Path(root) / ".omha" / "routing.jsonl" if not str(root).endswith(".jsonl") else Path(root)
    records = load(path)
    if not records:
        print(f"no routing records at {path}")
        return 1
    s = summarize(records)
    print(f"{path}  —  {s['turns']} turns")
    print(f"  ROUTE 누락 {s['missing']}  재라우팅 {s['rerouted']}  ANALYZE {s['analyze']}")
    for lane, n in s["lanes"].items():
        print(f"    {lane:22s} {n:4d}  {n / s['turns'] * 100:5.1f}%")
    missed = [r for r in records if r.get("missing")]
    if missed:
        print("  ROUTE 누락 턴 (앞 5개):")
        for r in missed[:5]:
            print(f"    · {r.get('prompt', '')[:70]}")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_cli(sys.argv))
