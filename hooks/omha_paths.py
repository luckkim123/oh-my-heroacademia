"""Single declaration point for this repo's on-disk root literal, `.omha`.

Every derived path hooks/*.py computes today (the redact-patterns denylist,
the routing.jsonl verdict log) is named here once. Callers delete their
inline `Path(cwd) / ".omha" / "..."` computation and call the matching
helper instead, importing it the same way the hooks already import each
other (`sys.path.insert(0, str(Path(__file__).resolve().parent))` then a
flat import — no new import mechanism).

P2 promise: **behavior-unchanged only.** `LEGACY_ROOT` is still `.omha` —
this repo's current legacy root, not the future unified `.hq/` store. Every
helper below returns exactly the path today's inline code already computed;
a helper that returns a different path is a bug, not an improvement. The
`.hq/` rename and its read-fallback are P3+ work and do not belong in this
module yet.

A re-entry lint (tests/test_omha_paths_lint.py) fails the build if a new
`.omha` literal is added anywhere outside this file.

Reference: ~/oh-my-orchestrator/skills/harness/references/store-spec.md §9.5.
"""
from __future__ import annotations

from pathlib import Path

LEGACY_ROOT = ".omha"


def root(base: Path) -> Path:
    """The `.omha/` directory itself, given the session/project `base`."""
    return Path(base) / LEGACY_ROOT


def redact_patterns_txt(base: Path) -> Path:
    """`.omha/redact-patterns.txt` under `base` — redact_guard's user-maintained
    denylist (hooks/redact_guard.py)."""
    return root(base) / "redact-patterns.txt"


def routing_jsonl(base: Path) -> Path:
    """`.omha/routing.jsonl` under `base` — the per-turn routing verdict log
    (hooks/route_log.py)."""
    return root(base) / "routing.jsonl"
