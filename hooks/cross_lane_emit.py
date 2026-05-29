"""omha PreToolUse hook: objective cross-lane signal detector (push channel).

This is the push counterpart to route_emit.py (the pull channel that injects
ROUTE on every UserPromptSubmit). Where the pull channel relies on the model
noticing it should re-route, this hook reads the *actual tool call payload*
and tells the model when a tool target belongs to a different lane than the
one currently in flight.

Design: 2026-05-29-omha-self-rerouting-design.md
  · matcher = Write | Edit | Skill (registered in plugin.json)
  · cards/*.json declare push signals in triggers.{extensions, skills}
  · stateless + 30s same-lane cooldown to avoid token-flood
  · hard tone — asks the model to prepend a STAGE re-route line, does NOT block
  · fail-open everywhere: missing cards / bad json / missing keys → exit 0 silent

Stdlib only — no a2a-sdk dependency.
"""
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Optional

CARDS_DIR = Path(__file__).resolve().parent.parent / "cards"
SEARCH_PATHS = [CARDS_DIR]
COOLDOWN_PATH = Path(tempfile.gettempdir()) / "omha_last_push.json"
COOLDOWN_SEC = 30.0


# ─── signal extraction ──────────────────────────────────────────────────────

def extract_signal(tool: str, tool_input: dict) -> Optional[dict]:
    """Pull a single concrete signal out of the tool call, or None.

    Write/Edit → file extension; Skill → bare skill name (namespace stripped).
    A file without an extension or a missing key returns None — better to be
    silent than to fabricate a signal.
    """
    if not isinstance(tool_input, dict):
        return None
    if tool in ("Write", "Edit"):
        fp = tool_input.get("file_path")
        if not isinstance(fp, str):
            return None
        ext = Path(fp).suffix
        if not ext:
            return None
        return {"kind": "extension", "value": ext}
    if tool == "Skill":
        skill = tool_input.get("skill")
        if not isinstance(skill, str) or not skill:
            return None
        # `plugin:skill` → bare `skill`. Cards declare bare names.
        bare = skill.split(":", 1)[1] if ":" in skill else skill
        return {"kind": "skill", "value": bare}
    return None


# ─── card discovery + lane match ────────────────────────────────────────────

def load_cards() -> List[dict]:
    """Stdlib-only JSON load across every SEARCH_PATHS dir. Returns [] on any error."""
    cards: List[dict] = []
    for d in SEARCH_PATHS:
        try:
            if not Path(d).is_dir():
                continue
            for path in sorted(Path(d).glob("*.json")):
                try:
                    cards.append(json.loads(path.read_text()))
                except (json.JSONDecodeError, OSError):
                    continue
        except OSError:
            continue
    return cards


def match_lane(signal: dict, cards: list) -> Optional[str]:
    """First card whose triggers contains this signal wins. None if unmapped.

    Silence on unmapped is intentional: the pull channel still handles cards
    that haven't opted in to push."""
    if not signal:
        return None
    kind, value = signal.get("kind"), signal.get("value")
    for card in cards:
        triggers = card.get("triggers") if isinstance(card, dict) else None
        if not isinstance(triggers, dict):
            continue
        bucket_name = "extensions" if kind == "extension" else "skills"
        bucket = triggers.get(bucket_name) or []
        if value in bucket:
            return card.get("name")
    return None


# ─── cooldown (stateless freshness gate) ────────────────────────────────────

def is_fresh(lane: str, now: Optional[float] = None) -> bool:
    """True if we should emit now: different lane, no record, or older than cooldown.

    Corrupt cooldown file → treat as fresh (fail-open). Never blocks emission
    because of state-store damage."""
    if now is None:
        now = time.time()
    try:
        last = json.loads(COOLDOWN_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return True
    if not isinstance(last, dict):
        return True
    if last.get("lane") != lane:
        return True
    try:
        ts = float(last.get("ts", 0.0))
    except (TypeError, ValueError):
        return True
    return (now - ts) >= COOLDOWN_SEC


def write_last_push(lane: str, now: Optional[float] = None) -> None:
    if now is None:
        now = time.time()
    try:
        COOLDOWN_PATH.write_text(json.dumps({"lane": lane, "ts": now}))
    except OSError:
        # Can't write cooldown? Skip silently — next call just re-emits, which
        # is noisier but not broken. Better than crashing the hook.
        pass


# ─── envelope ───────────────────────────────────────────────────────────────

def build_envelope(lane: str, signal: dict) -> dict:
    kind = signal.get("kind", "?")
    value = signal.get("value", "?")
    msg = (
        "⚠️ omha cross-lane signal detected.\n"
        f"· signal: {kind}={value}\n"
        f"· candidate lane: {lane}\n\n"
        "Prepend a STAGE re-routing line for this lane in your next text output "
        "(the relevant domain/harness plugin defines its STAGE format). "
        "The tool call proceeds — this is advisory routing context, not a block."
    )
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "additionalContext": msg}}


# ─── entrypoint ─────────────────────────────────────────────────────────────

def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError):
        return 0  # fail-open

    tool = payload.get("tool_name") if isinstance(payload, dict) else None
    tool_input = payload.get("tool_input") if isinstance(payload, dict) else None
    if not isinstance(tool, str) or not isinstance(tool_input, dict):
        return 0

    signal = extract_signal(tool, tool_input)
    if signal is None:
        return 0

    cards = load_cards()
    lane = match_lane(signal, cards)
    if lane is None:
        return 0

    if not is_fresh(lane):
        return 0

    write_last_push(lane)
    print(json.dumps(build_envelope(lane, signal)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
