#!/usr/bin/env python3
"""PreToolUse privacy backstop: warn (never block) before a PR/file-push tool
call sends a denylisted string outside the repo.

Sibling of hooks/route_guard.py — same fail-open contract, same stdin/stdout
JSON contract. The WARN envelope (non-blocking `additionalContext`, no
`permissionDecision`) follows hooks/cross_lane_emit.py's idiom rather than
route_guard's, since route_guard itself only knows binary allow/deny and this
backstop must never block a real PR — just flag it for review.

Scope (kept tight on purpose):
  - Bash commands that invoke `gh pr create` / `gh pr edit` -> scan the full
    command string
  - mcp__github__create_pull_request / mcp__github__create_or_update_file ->
    scan the title/body/content fields

Denylist: a user-maintained, gitignored, LITERAL line-based file at
`.omha/redact-patterns.txt` (relative to the tool call's cwd). Lines are
literal substrings, case-insensitive; '#' comments and blank lines are
ignored. Missing file -> silent allow. See .omha/redact-patterns.example.txt
for the committed placeholder template — the real file is user-created and
gitignored, never committed.

Known ceiling: `gh pr create --body-file <f>` carries the PR body OUTSIDE the
command string (in a file on disk), so a literal command-string scan misses
it. Not handled here — reading arbitrary --body-file targets off disk is a
bigger surface than this backstop is meant to cover.

Fails open on every error so a broken/missing denylist never blocks a real
tool call. Stdlib only.
"""
import json
import os
import re
import sys

DENYLIST_REL_PATH = os.path.join(".omha", "redact-patterns.txt")

_GH_PR_RE = re.compile(r"\bgh\s+pr\s+(create|edit)\b")

_MCP_TOOLS = ("mcp__github__create_pull_request", "mcp__github__create_or_update_file")


def load_patterns(cwd):
    """Read `.omha/redact-patterns.txt` under cwd -> list of literal lowercase
    patterns (comments/blanks stripped). Missing/unreadable file -> []
    (silent allow) — the caller treats an empty list as nothing to check."""
    path = os.path.join(cwd, DENYLIST_REL_PATH)
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return []
    patterns = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line.lower())
    return patterns


def find_match(text, patterns):
    """1-based index of the first pattern found as a substring of `text`
    (case-insensitive), or None if no pattern matches."""
    if not text:
        return None
    lowered = text.lower()
    for i, pat in enumerate(patterns, start=1):
        if pat in lowered:
            return i
    return None


def extract_payload(tool_name, tool_input):
    """Pull the outgoing text to scan out of the tool call, or None if this
    call is out of scope. The PreToolUse matcher should already exclude
    everything else, but this defends itself too (see cross_lane_emit's
    extract_signal for the same pattern)."""
    if not isinstance(tool_input, dict):
        return None
    if tool_name == "Bash":
        command = tool_input.get("command")
        if not isinstance(command, str) or not _GH_PR_RE.search(command):
            return None
        return command
    if tool_name in _MCP_TOOLS:
        parts = [tool_input.get(k) for k in ("title", "body", "content")]
        return "\n".join(p for p in parts if isinstance(p, str))
    return None


def build_warning(index):
    msg = (
        f"redact-guard: outgoing payload matches redact-patterns.txt line "
        f"{index}. Review before sending — this is advisory, not a block."
    )
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": msg}}


def run(stdin_obj):
    """Core gate. Returns a stdout dict (warn) or None (silent allow).
    Fails open: any exception here is caught by main()."""
    try:
        tool_name = stdin_obj.get("tool_name")
        tool_input = stdin_obj.get("tool_input")
        payload = extract_payload(tool_name, tool_input)
        if not payload:
            return None
        cwd = stdin_obj.get("cwd") or os.getcwd()
        patterns = load_patterns(cwd)
        if not patterns:
            return None
        index = find_match(payload, patterns)
        if index is None:
            return None
        return build_warning(index)
    except Exception:
        return None


def main():
    try:
        stdin_obj = json.load(sys.stdin)
    except Exception:
        return 0
    out = run(stdin_obj)
    if out is not None:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
