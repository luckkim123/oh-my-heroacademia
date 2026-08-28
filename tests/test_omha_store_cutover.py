"""P4 cutover acceptance — the four-state gate, new-path resolution, write
gating, and (omha's own wrinkle) the opt-in-by-directory contract that must
survive the `.hq` migration unchanged.

Mirrors oh-my-project's tests/test_omp_store_cutover.py (P3). Four gate-state
fixtures rather than a collapsed "migrated or not" because a three-state
design sends "legacy store present, no anchor" — the most dangerous state of
the migration — into the same quiet branch as "not an omha project at all".
`_write`'s middle branch (anchored, but this artifact not copied yet) gets
its own case for the same reason: a test that only checks "anchored writes
new, unanchored writes legacy" cannot see it.

The opt-in-by-directory block is omha-specific: `route_log.log_dir()` is
deliberately NOT anchor-gated (see omha_paths' module docstring), so its four
cases are checked directly against `route_log.log_dir`, not against
`omha_paths._write`.
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


# --- read resolution: new path when migrated, legacy when not ---------------

def test_every_helper_resolves_to_the_new_store_when_migrated(tmp_path):
    _seed_migrated(tmp_path)
    rt = tmp_path / ".hq" / "runtime" / "routing"
    assert omha_paths.redact_patterns_txt(tmp_path) == rt / "redact-patterns.txt"
    assert omha_paths.routing_jsonl(tmp_path) == rt / "routing.jsonl"


def test_every_helper_falls_back_when_only_the_legacy_store_exists(tmp_path):
    _seed_legacy(tmp_path)
    legacy = tmp_path / ".omha"
    assert omha_paths.redact_patterns_txt(tmp_path) == legacy / "redact-patterns.txt"
    assert omha_paths.routing_jsonl(tmp_path) == legacy / "routing.jsonl"


def test_fallback_is_per_file_not_per_directory(tmp_path):
    """A machine that pulled the anchor commit has the redact denylist copied
    into `.hq/runtime/routing/` but not yet the routing log — each file
    resolves on its own, not as a pair."""
    _seed_anchor(tmp_path)
    rt = tmp_path / ".hq" / "runtime" / "routing"
    rt.mkdir(parents=True)
    (rt / "redact-patterns.txt").write_text("new-pattern\n", encoding="utf-8")
    (tmp_path / ".omha").mkdir(parents=True)
    (tmp_path / ".omha" / "routing.jsonl").write_text('{"turn_id":"legacy"}\n',
                                                       encoding="utf-8")
    assert omha_paths.redact_patterns_txt(tmp_path) == rt / "redact-patterns.txt"
    assert omha_paths.routing_jsonl(tmp_path) == tmp_path / ".omha" / "routing.jsonl"


# --- write gating: the anchor decides, and a half-migrated root stays put ----

def test_write_goes_legacy_without_an_anchor(tmp_path):
    _seed_legacy(tmp_path)
    new = tmp_path / ".hq" / "runtime" / "routing" / "routing.jsonl"
    legacy = tmp_path / ".omha" / "routing.jsonl"
    assert omha_paths._write(tmp_path, new, legacy) == legacy


def test_write_goes_new_when_migrated(tmp_path):
    _seed_migrated(tmp_path)
    new = tmp_path / ".hq" / "runtime" / "routing" / "routing.jsonl"
    legacy = tmp_path / ".omha" / "routing.jsonl"
    assert omha_paths._write(tmp_path, new, legacy) == new


def test_write_stays_legacy_while_anchored_but_not_yet_copied(tmp_path):
    """The pilot's own window — the middle branch of `_write`. Seeding the
    anchor is step 0 and copying the files is step 2; a write landing in the
    new store in between would be invisible to every reader, which still
    resolves to the populated old one."""
    _seed_legacy(tmp_path)
    legacy = tmp_path / ".omha" / "routing.jsonl"
    _seed_anchor(tmp_path)
    new = tmp_path / ".hq" / "runtime" / "routing" / "routing.jsonl"
    assert omha_paths._write(tmp_path, new, legacy) == legacy


def test_write_goes_new_for_a_project_anchored_from_scratch(tmp_path):
    """Neither path holds the artifact and there is no legacy store to
    orphan — this is the only case where the new path wins by default."""
    _seed_anchor(tmp_path)
    new = tmp_path / ".hq" / "runtime" / "routing" / "routing.jsonl"
    legacy = tmp_path / ".omha" / "routing.jsonl"
    assert omha_paths._write(tmp_path, new, legacy) == new


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
