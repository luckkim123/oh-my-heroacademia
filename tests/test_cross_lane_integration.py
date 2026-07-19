"""Cross-lane push integration scenarios (plan §4 + §5.2.b).

These mirror the live `claude -p` scenarios from the execution plan, but run
fully under pytest with fixture cards in tmp_path. Real OMD/OMS plugin card
integration (i.e. hook discovering ~/.claude/plugins/*/cards/*.json) is left
as a follow-on task — for now SEARCH_PATHS holds only omha cards, and these
tests inject fixture domain cards via monkeypatch.

Scenario coverage (design §7.2):
  A. unmapped extension → silent (no false push on note.md)
  B. cross-lane signal → emit (the user's `.tex inside OMD` symptom)
  C. cooldown → first emits, repeat is suppressed, mixed lanes both emit
  D. unregistered local skill → silent (cards-as-opt-in contract)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))
import cross_lane_emit as cle

# ─── fixture cards ───────────────────────────────────────────────────────────

def _setup_domain_cards(tmp_path, monkeypatch):
    """Plant fixture OMD + OMS cards next to the omha SP/OMC cards.
    Tests then run cle.main() as if installed alongside real domain plugins."""
    cards_dir = tmp_path / "cards"
    cards_dir.mkdir()
    (cards_dir / "omd.json").write_text(json.dumps({
        "name": "oh-my-docs", "description": "Document domain.",
        "triggers": {"extensions": [".docx", ".pptx", ".hwpx"],
                     "skills": ["docs-build", "docs-pilot", "docs-verify"]}}))
    (cards_dir / "oms.json").write_text(json.dumps({
        "name": "oh-my-scholar", "description": "Paper domain.",
        "triggers": {"extensions": [".tex", ".bib"],
                     "skills": ["scholar-draft", "scholar-pilot"]}}))
    cd = tmp_path / "cooldown.json"
    monkeypatch.setattr(cle, "CARDS_DIR", cards_dir)
    monkeypatch.setattr(cle, "SEARCH_PATHS", [cards_dir])
    monkeypatch.setattr(cle, "COOLDOWN_PATH", cd)
    return cards_dir, cd


def _run(monkeypatch, capsys, tool_name, tool_input):
    """Drive cle.main() with a synthetic stdin payload, return the printed string."""
    payload = {"tool_name": tool_name, "tool_input": tool_input}
    monkeypatch.setattr("sys.stdin", _Stdin(json.dumps(payload)))
    rc = cle.main()
    assert rc == 0, "hook must exit 0 so tool call proceeds"
    return capsys.readouterr().out


class _Stdin:
    def __init__(self, data: str):
        self._data = data
    def read(self) -> str:
        return self._data


# ─── scenario A: unmapped extension → silent ────────────────────────────────

def test_scenario_A_unmapped_extension_is_silent(tmp_path, monkeypatch, capsys):
    """User edits note.md while working in OMD. note.md isn't in any card's
    extensions → push is silent. (Pull/model judgment still applies; this hook
    only fires on registered signals.)"""
    _setup_domain_cards(tmp_path, monkeypatch)
    out = _run(monkeypatch, capsys, "Write", {"file_path": "/work/note.md"})
    assert out.strip() == ""


# ─── scenario B: cross-lane signal → emit ───────────────────────────────────

def test_scenario_B_cross_lane_extension_emits(tmp_path, monkeypatch, capsys):
    """The exact user symptom — working in OMD, suddenly hits a .tex file.
    The hook must surface this as an OMS-lane signal so the model re-routes
    instead of doing OMS work as if it were OMD."""
    _setup_domain_cards(tmp_path, monkeypatch)
    out = _run(monkeypatch, capsys, "Write", {"file_path": "/papers/intro.tex"})
    env = json.loads(out)
    ctx = env["hookSpecificOutput"]["additionalContext"]
    assert "oh-my-scholar" in ctx
    assert ".tex" in ctx
    assert "STAGE" in ctx  # hard tone asks model to re-route in next output


def test_scenario_B_cross_lane_skill_emits(tmp_path, monkeypatch, capsys):
    """Same intent, different signal: Skill invocation."""
    _setup_domain_cards(tmp_path, monkeypatch)
    out = _run(monkeypatch, capsys, "Skill", {"skill": "oh-my-scholar:scholar-draft"})
    env = json.loads(out)
    ctx = env["hookSpecificOutput"]["additionalContext"]
    assert "oh-my-scholar" in ctx
    assert "scholar-draft" in ctx


# ─── scenario C: cooldown ───────────────────────────────────────────────────

def test_scenario_C_same_lane_repeat_is_suppressed(tmp_path, monkeypatch, capsys):
    """5 consecutive .pptx Writes within cooldown → emit once, suppress 4.
    Without this the model gets 5 identical advisory blocks back-to-back =
    token-flood + noise."""
    _setup_domain_cards(tmp_path, monkeypatch)
    emissions = 0
    for i in range(5):
        out = _run(monkeypatch, capsys, "Write", {"file_path": f"/deck/slide{i}.pptx"})
        if out.strip():
            emissions += 1
    assert emissions == 1, f"expected 1 emit, got {emissions}"


def test_scenario_C_cross_lane_in_middle_re_emits(tmp_path, monkeypatch, capsys):
    """If the user *switches* lane mid-stream, the cooldown does not apply.
    Sequence: OMD → OMD (suppressed) → OMS (emits!) → OMS (suppressed)."""
    _setup_domain_cards(tmp_path, monkeypatch)
    out1 = _run(monkeypatch, capsys, "Write", {"file_path": "/a.pptx"})  # emit
    out2 = _run(monkeypatch, capsys, "Write", {"file_path": "/b.pptx"})  # suppress
    out3 = _run(monkeypatch, capsys, "Write", {"file_path": "/c.tex"})   # emit (different lane)
    out4 = _run(monkeypatch, capsys, "Write", {"file_path": "/d.tex"})   # suppress
    assert out1.strip() and "oh-my-docs" in out1
    assert out2.strip() == ""
    assert out3.strip() and "oh-my-scholar" in out3
    assert out4.strip() == ""


# ─── scenario D: unregistered local skill → silent ──────────────────────────

def test_scenario_D_unregistered_skill_is_silent(tmp_path, monkeypatch, capsys):
    """User invokes a local skill that no card has declared. The hook stays
    silent — push is opt-in per cards. Pull/model still sees it via the
    skill's own SKILL.md description."""
    _setup_domain_cards(tmp_path, monkeypatch)
    out = _run(monkeypatch, capsys, "Skill", {"skill": "my-local-custom-skill"})
    assert out.strip() == ""


# ─── bonus: confirm SP/OMC skill triggers (planted in T1) work end-to-end ───

def test_sp_skill_routes_to_superpowers(tmp_path, monkeypatch, capsys):
    """T1 added writing-plans/test-driven-development to SP card. End-to-end
    confirmation that the hook honors the omha SP/OMC cards themselves —
    not just fixture cards — when SEARCH_PATHS includes the real cards dir."""
    real_cards = Path(__file__).parent.parent / "cards"
    monkeypatch.setattr(cle, "SEARCH_PATHS", [real_cards])
    monkeypatch.setattr(cle, "COOLDOWN_PATH", tmp_path / "cd.json")
    out = _run(monkeypatch, capsys, "Skill", {"skill": "writing-plans"})
    env = json.loads(out)
    assert "superpowers" in env["hookSpecificOutput"]["additionalContext"]


def test_omc_skill_routes_to_oh_my_claudecode(tmp_path, monkeypatch, capsys):
    real_cards = Path(__file__).parent.parent / "cards"
    monkeypatch.setattr(cle, "SEARCH_PATHS", [real_cards])
    monkeypatch.setattr(cle, "COOLDOWN_PATH", tmp_path / "cd.json")
    out = _run(monkeypatch, capsys, "Skill", {"skill": "ultrawork"})
    env = json.loads(out)
    assert "oh-my-claudecode" in env["hookSpecificOutput"]["additionalContext"]
