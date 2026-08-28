"""P4/P7 cutover acceptance — the four-state gate, anchor-only resolution
(store-spec §7 stage 2), and (omha's own wrinkle) the opt-in-by-directory
contract that must survive the `.hq` migration unchanged.

Mirrors oh-my-project's tests/test_omp_store_cutover.py. Four gate-state
fixtures rather than a collapsed "migrated or not" because a three-state
design sends "legacy store present, no anchor" — the most dangerous state of
the migration — into the same quiet branch as "not an omha project at all".

Stage 2 replaced the existence-checking `_read`/`_write` pair with a single
`_resolve(base, new, legacy)`: `has_anchor(base)` alone decides, in both
directions, regardless of whether either path actually exists on disk. The
stage-1 middle branch this file used to test — an anchored project staying
on legacy until its files were copied — is gone; the tests below assert the
opposite of that now, directly.

The opt-in-by-directory block is omha-specific: `route_log.log_dir()` is
deliberately NOT anchor-gated (see omha_paths' module docstring), so its four
cases are checked directly against `route_log.log_dir`, not against
`omha_paths._resolve`.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))
import omha_paths  # noqa: E402
import route_log  # noqa: E402


def _seed_anchor(base, text="id: fixture\n"):
    (base / ".hq").mkdir(parents=True, exist_ok=True)
    (base / ".hq" / ".anchor").write_text(text, encoding="utf-8")


def _seed_legacy(base):
    (base / ".omha").mkdir(parents=True, exist_ok=True)
    (base / ".omha" / "redact-patterns.txt").write_text("legacy-pattern\n", encoding="utf-8")
    (base / ".omha" / "routing.jsonl").write_text('{"turn_id":"legacy"}\n', encoding="utf-8")


def _seed_migrated(base):
    """A fully cut-over anchor: anchor + the routing runtime layer populated."""
    _seed_anchor(base)
    rt = base / ".hq" / "runtime" / "routing"
    rt.mkdir(parents=True, exist_ok=True)
    (rt / "redact-patterns.txt").write_text("new-pattern\n", encoding="utf-8")
    (rt / "routing.jsonl").write_text('{"turn_id":"new"}\n', encoding="utf-8")


# --- the four gate states ---------------------------------------------------

def test_gate_off(tmp_path):
    assert omha_paths.gate_state(tmp_path) == omha_paths.GATE_OFF


def test_gate_legacy(tmp_path):
    _seed_legacy(tmp_path)
    assert omha_paths.gate_state(tmp_path) == omha_paths.GATE_LEGACY


def test_gate_normal(tmp_path):
    _seed_anchor(tmp_path)
    assert omha_paths.gate_state(tmp_path) == omha_paths.GATE_NORMAL


@pytest.mark.parametrize("bad", [
    "id: a\nid: b\n",          # two lines
    "vault\n",                 # missing the id: prefix
    "id:   \n",                # empty value
    "",                        # empty file
])
def test_gate_corrupt(tmp_path, bad):
    _seed_anchor(tmp_path, bad)
    assert omha_paths.gate_state(tmp_path) == omha_paths.GATE_CORRUPT


def test_gate_corrupt_beats_legacy(tmp_path):
    """A broken anchor next to a populated legacy store is corrupt, not
    legacy — read anchor-first, or a typo would silently look like 'not yet
    migrated' and keep writing to the old store forever."""
    _seed_legacy(tmp_path)
    _seed_anchor(tmp_path, "id: a\nid: b\n")
    assert omha_paths.gate_state(tmp_path) == omha_paths.GATE_CORRUPT


# --- getter-level resolution: anchor present -> new, absent -> legacy -------

def test_every_helper_resolves_to_the_new_store_when_migrated(tmp_path):
    _seed_migrated(tmp_path)
    rt = tmp_path / ".hq" / "runtime" / "routing"
    assert omha_paths.redact_patterns_txt(tmp_path) == rt / "redact-patterns.txt"
    assert omha_paths.routing_jsonl(tmp_path) == rt / "routing.jsonl"


def test_every_helper_resolves_to_legacy_when_unanchored(tmp_path):
    _seed_legacy(tmp_path)
    legacy = tmp_path / ".omha"
    assert omha_paths.redact_patterns_txt(tmp_path) == legacy / "redact-patterns.txt"
    assert omha_paths.routing_jsonl(tmp_path) == legacy / "routing.jsonl"


# --- _resolve directly: no existence check in either direction --------------

def test_resolve_goes_legacy_without_an_anchor(tmp_path):
    _seed_legacy(tmp_path)
    new = tmp_path / ".hq" / "runtime" / "routing" / "routing.jsonl"
    legacy = tmp_path / ".omha" / "routing.jsonl"
    assert omha_paths._resolve(tmp_path, new, legacy) == legacy


def test_resolve_goes_new_when_migrated(tmp_path):
    _seed_migrated(tmp_path)
    new = tmp_path / ".hq" / "runtime" / "routing" / "routing.jsonl"
    legacy = tmp_path / ".omha" / "routing.jsonl"
    assert omha_paths._resolve(tmp_path, new, legacy) == new


def test_resolve_goes_new_for_a_project_anchored_from_scratch(tmp_path):
    """Neither path holds the artifact and there is no legacy store to
    orphan — the anchor alone is still sufficient."""
    _seed_anchor(tmp_path)
    new = tmp_path / ".hq" / "runtime" / "routing" / "routing.jsonl"
    legacy = tmp_path / ".omha" / "routing.jsonl"
    assert omha_paths._resolve(tmp_path, new, legacy) == new


def test_resolve_returns_new_for_anchored_project_with_only_legacy_file(tmp_path):
    """Stage 2's whole point, inverted from what stage 1 asserted: an
    anchored project resolves to `.hq/` even when only the legacy file
    exists on disk and the new path has nothing copied to it yet. Stage 1
    kept this case on legacy (the anchored-but-not-yet-copied window);
    stage 2 declares that window closed."""
    _seed_legacy(tmp_path)
    _seed_anchor(tmp_path)
    new = tmp_path / ".hq" / "runtime" / "routing" / "routing.jsonl"
    legacy = tmp_path / ".omha" / "routing.jsonl"
    assert omha_paths._resolve(tmp_path, new, legacy) == new


def test_resolve_returns_legacy_for_unanchored_project_with_legacy_file(tmp_path):
    """The unanchored mirror of the case above: no anchor at all means
    legacy, regardless of what exists on disk."""
    _seed_legacy(tmp_path)
    new = tmp_path / ".hq" / "runtime" / "routing" / "routing.jsonl"
    legacy = tmp_path / ".omha" / "routing.jsonl"
    assert omha_paths._resolve(tmp_path, new, legacy) == legacy


# --- opt-in by directory: omha's own wrinkle, unchanged by the cutover ------

def test_log_dir_anchor_alone_does_not_turn_logging_on(tmp_path):
    """(a) An anchor with neither `.hq/runtime/routing/` nor `.omha/` yet
    created means logging is OFF — the anchor is never the switch here."""
    _seed_anchor(tmp_path)
    assert route_log.log_dir(str(tmp_path)) is None


def test_log_dir_legacy_directory_turns_logging_on(tmp_path):
    """(b) `.omha/` alone (pre-migration, no anchor) still turns it on."""
    (tmp_path / ".omha").mkdir()
    assert route_log.log_dir(str(tmp_path)) == tmp_path / ".omha"


def test_log_dir_new_runtime_directory_turns_logging_on(tmp_path):
    """(c) `.hq/runtime/routing/` existing turns it on, new path preferred."""
    rt = tmp_path / ".hq" / "runtime" / "routing"
    rt.mkdir(parents=True)
    assert route_log.log_dir(str(tmp_path)) == rt


def test_log_dir_empty_cwd_is_off():
    """(d) No cwd -> off, never a getcwd() guess."""
    assert route_log.log_dir("") is None
    assert route_log.log_dir(None) is None
