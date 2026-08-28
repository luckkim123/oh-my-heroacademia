"""Single declaration point for this repo's on-disk root literals — the
unified store `.hq` and the legacy store `.omha`.

Every derived path hooks/*.py computes (the redact-patterns denylist, the
routing.jsonl verdict log) is named here once. Callers never join a root
literal themselves; a re-entry lint (tests/test_omha_paths_lint.py) fails the
build if either literal appears anywhere outside this file.

Reference: ~/oh-my-orchestrator/skills/harness/references/store-spec.md
  §3 the four layers · §6 the four-state gate · §7 fallback · §9.3 omha's
  per-file layer assignment · §9.5 the six declaration sites.

P4 (2026-08-28) switches this module from "legacy only" to the cutover shape,
mirroring oh-my-project's P3 (`omp_paths.py`). The same three rules govern
every helper below:

**1. The anchor is the switch for writes, not the release.** A write goes to
`.hq/` when — and only when — the project root carries a parseable
`.hq/.anchor`. Without one it goes to `.omha/`, exactly where it went before.

**2. Reads resolve per file, new first, legacy second.** Not per directory:
existence of the specific new path is the only test.

**3. The layer is per file** (§3). omha's two artifacts split across two
layers: `redact-patterns.txt` -> `runtime/routing/` (a personal string, rule
①), `routing.jsonl` -> `runtime/routing/` (a machine-local log, rule ⑤). Both
land in the same directory here, unlike omp's fan-out across four.

**omha carries one exception to rule 1 that this cutover must not disturb:**
`route_log.py`'s **opt-in by directory** contract predates the unified store
and stays unchanged underneath it. Logging turns on when the *routing
runtime directory* exists — `.hq/runtime/routing/` or, pre-migration,
`.omha/` — never merely because an anchor is present. An anchored root with
neither directory created yet is *off*, exactly like an un-anchored root with
no `.omha/`. `route_log.log_dir()` checks `runtime_dir()`/`root()` directly
for this reason, rather than routing through the generic `_write` gate below:
`_write` treats a valid anchor as sufficient to prefer the new path, and that
is exactly the behavior this contract forbids.
"""
from __future__ import annotations

import re
from pathlib import Path

HQ_ROOT = ".hq"
LEGACY_ROOT = ".omha"

# --- layer roots (store-spec section 3, omha's routing scope) ---------------

ANCHOR_REL = f"{HQ_ROOT}/.anchor"
_CONFIG_REL = f"{HQ_ROOT}/config/routing"
_COMMUNITY_REL = f"{HQ_ROOT}/community"
_RUNTIME_REL = f"{HQ_ROOT}/runtime/routing"
_WORK_REL = f"{HQ_ROOT}/work/routing"

_ANCHOR_ID_RE = re.compile(r"^id:\s*(\S.*)$")


def root(base: Path) -> Path:
    """The legacy `.omha/` directory itself, given the session/project `base`."""
    return Path(base) / LEGACY_ROOT


def anchor_file(base: Path) -> Path:
    return Path(base) / ANCHOR_REL


def config_dir(base: Path) -> Path:
    return Path(base) / _CONFIG_REL


def community_dir(base: Path) -> Path:
    return Path(base) / _COMMUNITY_REL


def runtime_dir(base: Path) -> Path:
    return Path(base) / _RUNTIME_REL


def work_dir(base: Path) -> Path:
    return Path(base) / _WORK_REL


def migrated_jsonl(base: Path) -> Path:
    """The anchor-wide migration ledger — `config/`, not `config/routing/`:
    it is shared across harnesses (store-spec section 2)."""
    return Path(base) / HQ_ROOT / "config" / "migrated.jsonl"


# --- anchor parse and the four-state gate (store-spec sections 2 and 6) -----

class AnchorError(Exception):
    """The anchor file exists but does not parse — a corrupt store, never an
    absent one."""


def parse_anchor_id(path: Path) -> str:
    """Exactly one non-empty line `id: <value>` after stripping one trailing
    newline. Anything else raises. Deliberately a 10-line reimplementation of
    oh-my-orchestrator's `hq.anchor.parse_anchor` rather than a cross-plugin
    import: omha cannot assume oh-my-orchestrator is installed, and an
    ImportError in a routing hook is a worse failure than a duplicated
    regex."""
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise AnchorError(f"{path}: cannot read anchor file: {e}") from e
    text = raw[:-1] if raw.endswith("\n") else raw
    non_empty = [ln for ln in text.split("\n") if ln.strip() != ""]
    if len(non_empty) != 1:
        raise AnchorError(
            f"{path}: expected exactly one non-empty line, found {len(non_empty)}")
    m = _ANCHOR_ID_RE.match(non_empty[0])
    if not m:
        raise AnchorError(
            f"{path}: line does not match 'id: <value>': {non_empty[0]!r}")
    value = m.group(1).strip()
    if not value:
        raise AnchorError(f"{path}: empty id value")
    return value


def has_anchor(base: Path) -> bool:
    """True when `base` carries a *parseable* anchor. An unparseable one is
    False here and `corrupt` in `gate_state` — the write switch must not flip
    on a broken file."""
    f = anchor_file(base)
    if not f.is_file():
        return False
    try:
        parse_anchor_id(f)
        return True
    except AnchorError:
        return False


def has_legacy_store(base: Path) -> bool:
    return root(base).is_dir()


def has_store(base: Path) -> bool:
    """True when `base` is an omha project under either store."""
    return anchor_file(base).is_file() or has_legacy_store(base)


GATE_OFF = "off"
GATE_LEGACY = "legacy"
GATE_NORMAL = "normal"
GATE_CORRUPT = "corrupt"


def gate_state(base: Path) -> str:
    """store-spec section 6, the pair (legacy store, anchor) — never a single
    marker.

    off      no legacy store, no anchor   — not an omha project; hooks exit 0
    legacy   legacy store, no anchor      — warn, read via fallback
    normal   anchor present and parseable
    corrupt  anchor present, unparseable  — loud, never silent
    """
    f = anchor_file(base)
    if f.is_file():
        try:
            parse_anchor_id(f)
            return GATE_NORMAL
        except AnchorError:
            return GATE_CORRUPT
    return GATE_LEGACY if has_legacy_store(base) else GATE_OFF


# --- resolution: read new-then-legacy, write anchor-gated -------------------

def _read(new: Path, legacy: Path) -> Path:
    """Rule 2. Existence of the specific new path is the whole test."""
    return new if new.exists() else legacy


def _write(base: Path, new: Path, legacy: Path) -> Path:
    """Rule 1. The anchor, not the release, decides — and an anchored root
    whose files have not been copied yet keeps writing where the content
    still is (the middle branch: anchored, new path still empty, legacy
    still populated -> legacy)."""
    if not has_anchor(base):
        return legacy
    if new.exists():
        return new
    return legacy if legacy.exists() else new


# --- runtime/routing/ layer --------------------------------------------------

def redact_patterns_txt(base: Path) -> Path:
    """`redact-patterns.txt` — read-resolving. User-maintained and gitignored
    in both stores; nothing in this repo writes it, so there is no write
    form."""
    return _read(runtime_dir(base) / "redact-patterns.txt",
                 root(base) / "redact-patterns.txt")


def routing_jsonl(base: Path) -> Path:
    """`routing.jsonl` — read-resolving, for readers (`route_log._cli`).
    Writers use `route_log.log_dir()` instead — see the opt-in-by-directory
    note in this module's docstring; the write path is never anchor-gated."""
    return _read(runtime_dir(base) / "routing.jsonl", root(base) / "routing.jsonl")
