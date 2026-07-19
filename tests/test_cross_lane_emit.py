"""PreToolUse push hook: cross_lane_emit.py.

Stateless + cooldown design (see 2026-05-29-omha-self-rerouting-design §4).
Reads cards/*.json triggers, matches tool_input signals, emits a hard-toned
hookSpecificOutput envelope. Cooldown (30s same-lane) prevents token-flood
when a task does many consecutive operations in the same lane.

Test groups mirror plan §2.1:
  1. extract_signal — file extension / skill name extraction
  2. match_lane — signal → lane via cards.triggers
  3. cooldown — stateless freshness gate
  4. e2e — stdin → stdout envelope
  5. fail-open — missing cards / bad json / no tool_input never blocks session
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))
import cross_lane_emit as cle

# ─── group 1: extract_signal ─────────────────────────────────────────────────

def test_write_extracts_file_extension():
    s = cle.extract_signal("Write", {"file_path": "/tmp/intro.tex"})
    assert s == {"kind": "extension", "value": ".tex"}


def test_edit_extracts_file_extension():
    s = cle.extract_signal("Edit", {"file_path": "/x/y/slides.docx"})
    assert s == {"kind": "extension", "value": ".docx"}


def test_skill_extracts_bare_name_when_namespaced():
    """`oh-my-scholar:scholar-draft` → skill = `scholar-draft`.
    Cards declare bare skill names so the namespace is stripped at the boundary."""
    s = cle.extract_signal("Skill", {"skill": "oh-my-scholar:scholar-draft"})
    assert s == {"kind": "skill", "value": "scholar-draft"}


def test_skill_extracts_bare_name_when_unnamespaced():
    s = cle.extract_signal("Skill", {"skill": "ultrawork"})
    assert s == {"kind": "skill", "value": "ultrawork"}


def test_write_with_no_extension_returns_none():
    """`Makefile`, `README` have no extension — no card maps them — return None
    rather than make up an extension."""
    assert cle.extract_signal("Write", {"file_path": "/repo/Makefile"}) is None


def test_unhandled_tool_returns_none():
    """matcher should keep Bash out, but the function defends itself anyway."""
    assert cle.extract_signal("Bash", {"command": "ls"}) is None


def test_missing_input_keys_returns_none():
    assert cle.extract_signal("Write", {}) is None
    assert cle.extract_signal("Skill", {}) is None


# ─── group 2: match_lane ─────────────────────────────────────────────────────

def _make_cards():
    return [
        {"name": "oh-my-claudecode",
         "triggers": {"extensions": [], "skills": ["ultrawork", "ralph"]}},
        {"name": "oh-my-scholar",
         "triggers": {"extensions": [".tex", ".bib"], "skills": ["scholar-draft"]}},
        {"name": "oh-my-docs",
         "triggers": {"extensions": [".docx", ".pptx"], "skills": ["docs-build"]}},
    ]


def test_match_extension_to_lane():
    cards = _make_cards()
    assert cle.match_lane({"kind": "extension", "value": ".tex"}, cards) == "oh-my-scholar"
    assert cle.match_lane({"kind": "extension", "value": ".docx"}, cards) == "oh-my-docs"


def test_match_skill_to_lane():
    cards = _make_cards()
    assert cle.match_lane({"kind": "skill", "value": "ultrawork"}, cards) == "oh-my-claudecode"
    assert cle.match_lane({"kind": "skill", "value": "scholar-draft"}, cards) == "oh-my-scholar"


def test_unmapped_signal_returns_none():
    """The whole point of the push channel is silence on unmapped signals —
    pull (model judgment) still covers them. No false push."""
    cards = _make_cards()
    assert cle.match_lane({"kind": "extension", "value": ".rs"}, cards) is None
    assert cle.match_lane({"kind": "skill", "value": "my-custom-local"}, cards) is None


def test_cards_without_triggers_block_are_skipped():
    """A card may omit triggers entirely — push is opt-in."""
    cards = [{"name": "legacy", "description": "no triggers"}]
    assert cle.match_lane({"kind": "extension", "value": ".tex"}, cards) is None


# ─── group 3: cooldown ───────────────────────────────────────────────────────

def test_first_call_passes_and_records(tmp_path, monkeypatch):
    cd = tmp_path / "cooldown.json"
    monkeypatch.setattr(cle, "COOLDOWN_PATH", cd)
    assert cle.is_fresh("oh-my-docs", now=1000.0) is True
    cle.write_last_push("oh-my-docs", now=1000.0)
    assert cd.exists()


def test_same_lane_within_cooldown_is_stale(tmp_path, monkeypatch):
    cd = tmp_path / "cooldown.json"
    monkeypatch.setattr(cle, "COOLDOWN_PATH", cd)
    cle.write_last_push("oh-my-docs", now=1000.0)
    assert cle.is_fresh("oh-my-docs", now=1010.0) is False  # 10s < 30s


def test_same_lane_after_cooldown_is_fresh(tmp_path, monkeypatch):
    cd = tmp_path / "cooldown.json"
    monkeypatch.setattr(cle, "COOLDOWN_PATH", cd)
    cle.write_last_push("oh-my-docs", now=1000.0)
    assert cle.is_fresh("oh-my-docs", now=1040.0) is True  # 40s > 30s


def test_different_lane_is_immediately_fresh(tmp_path, monkeypatch):
    """The whole point: transition is the strong signal. No cooldown across lanes."""
    cd = tmp_path / "cooldown.json"
    monkeypatch.setattr(cle, "COOLDOWN_PATH", cd)
    cle.write_last_push("oh-my-docs", now=1000.0)
    assert cle.is_fresh("oh-my-scholar", now=1005.0) is True


def test_corrupt_cooldown_file_is_fail_open(tmp_path, monkeypatch):
    cd = tmp_path / "cooldown.json"
    cd.write_text("not json {{{")
    monkeypatch.setattr(cle, "COOLDOWN_PATH", cd)
    assert cle.is_fresh("oh-my-docs", now=1000.0) is True


# ─── group 4: e2e via stdin/stdout ───────────────────────────────────────────

def test_e2e_write_emits_envelope_for_mapped_extension(tmp_path, monkeypatch, capsys):
    cards_dir = tmp_path / "cards"
    cards_dir.mkdir()
    (cards_dir / "omd.json").write_text(json.dumps({
        "name": "oh-my-docs", "description": "Document domain.",
        "triggers": {"extensions": [".docx"], "skills": []}}))
    cd = tmp_path / "cd.json"
    monkeypatch.setattr(cle, "CARDS_DIR", cards_dir)
    monkeypatch.setattr(cle, "COOLDOWN_PATH", cd)
    monkeypatch.setattr(cle, "SEARCH_PATHS", [cards_dir])

    payload = {"tool_name": "Write", "tool_input": {"file_path": "/x.docx"}}
    monkeypatch.setattr("sys.stdin", _Stdin(json.dumps(payload)))
    rc = cle.main()
    assert rc == 0

    out = capsys.readouterr().out
    assert out.strip(), "should emit hookSpecificOutput envelope"
    env = json.loads(out)
    assert env["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    ctx = env["hookSpecificOutput"]["additionalContext"]
    assert "oh-my-docs" in ctx
    assert ".docx" in ctx
    assert "STAGE" in ctx  # hard tone asks model to prepend STAGE re-route


def test_e2e_unmapped_extension_is_silent(tmp_path, monkeypatch, capsys):
    cards_dir = tmp_path / "cards"
    cards_dir.mkdir()
    (cards_dir / "omd.json").write_text(json.dumps({
        "name": "oh-my-docs", "description": "d",
        "triggers": {"extensions": [".docx"], "skills": []}}))
    monkeypatch.setattr(cle, "CARDS_DIR", cards_dir)
    monkeypatch.setattr(cle, "COOLDOWN_PATH", tmp_path / "cd.json")
    monkeypatch.setattr(cle, "SEARCH_PATHS", [cards_dir])

    payload = {"tool_name": "Write", "tool_input": {"file_path": "/x.md"}}
    monkeypatch.setattr("sys.stdin", _Stdin(json.dumps(payload)))
    cle.main()
    assert capsys.readouterr().out.strip() == ""


def test_e2e_cooldown_suppresses_repeat(tmp_path, monkeypatch, capsys):
    cards_dir = tmp_path / "cards"
    cards_dir.mkdir()
    (cards_dir / "omd.json").write_text(json.dumps({
        "name": "oh-my-docs", "description": "d",
        "triggers": {"extensions": [".docx"], "skills": []}}))
    monkeypatch.setattr(cle, "CARDS_DIR", cards_dir)
    monkeypatch.setattr(cle, "COOLDOWN_PATH", tmp_path / "cd.json")
    monkeypatch.setattr(cle, "SEARCH_PATHS", [cards_dir])

    payload = {"tool_name": "Write", "tool_input": {"file_path": "/a.docx"}}
    monkeypatch.setattr("sys.stdin", _Stdin(json.dumps(payload)))
    cle.main()
    first = capsys.readouterr().out
    assert first.strip(), "first call must emit"

    monkeypatch.setattr("sys.stdin", _Stdin(json.dumps(payload)))
    cle.main()
    second = capsys.readouterr().out
    assert second.strip() == "", "second call within cooldown must be silent"


# ─── group 5: fail-open ──────────────────────────────────────────────────────

def test_missing_cards_dir_is_fail_open(tmp_path, monkeypatch, capsys):
    """A missing cards directory should never block the tool call.
    Better to skip push than to halt the session."""
    monkeypatch.setattr(cle, "CARDS_DIR", tmp_path / "nope")
    monkeypatch.setattr(cle, "SEARCH_PATHS", [tmp_path / "nope"])
    monkeypatch.setattr(cle, "COOLDOWN_PATH", tmp_path / "cd.json")
    payload = {"tool_name": "Write", "tool_input": {"file_path": "/x.docx"}}
    monkeypatch.setattr("sys.stdin", _Stdin(json.dumps(payload)))
    rc = cle.main()
    assert rc == 0
    assert capsys.readouterr().out.strip() == ""


def test_garbage_stdin_is_fail_open(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cle, "CARDS_DIR", tmp_path)
    monkeypatch.setattr(cle, "SEARCH_PATHS", [tmp_path])
    monkeypatch.setattr(cle, "COOLDOWN_PATH", tmp_path / "cd.json")
    monkeypatch.setattr("sys.stdin", _Stdin("not json {{{"))
    rc = cle.main()
    assert rc == 0
    assert capsys.readouterr().out.strip() == ""


def test_hook_has_no_third_party_imports():
    """Stdlib only — same discipline as route_emit.py. a2a, requests, etc. not allowed."""
    src = (Path(__file__).parent.parent / "hooks" / "cross_lane_emit.py").read_text()
    for forbidden in ("import a2a", "from a2a", "import requests", "import yaml"):
        assert forbidden not in src, f"unexpected import: {forbidden}"


# ─── test helper ─────────────────────────────────────────────────────────────

class _Stdin:
    """Minimal stdin replacement for monkeypatch — only `.read()` is used."""
    def __init__(self, data: str):
        self._data = data
    def read(self) -> str:
        return self._data
