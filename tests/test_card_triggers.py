"""Card schema: optional `triggers` block for PreToolUse push routing.

Cards may declare objective push signals: file extensions (e.g. ".tex" → OMS)
and skill names (e.g. "scholar-draft" → OMS). The cross_lane_emit hook reads
these to flip lanes mid-task. Backwards-compatible: missing `triggers` → empty.
"""
from pathlib import Path
from omha.registry import AgentTriggers, load_cards

CARDS_DIR = Path(__file__).parent.parent / "cards"


def test_sp_and_omc_cards_declare_triggers_skills():
    cards = {c.name: c for c in load_cards(CARDS_DIR)}
    for name in ("superpowers", "oh-my-claudecode"):
        c = cards[name]
        assert isinstance(c.triggers, AgentTriggers)
        assert c.triggers.skills, f"{name} should list characteristic push skills"
        assert all(isinstance(s, str) for s in c.triggers.skills)


def test_sp_and_omc_have_no_extension_triggers():
    """SP/OMC are *work-style* lanes — file extensions belong to domain cards
    (OMD/OMS/etc.), not here. Asserting empty makes the contract explicit."""
    cards = {c.name: c for c in load_cards(CARDS_DIR)}
    for name in ("superpowers", "oh-my-claudecode"):
        assert cards[name].triggers.extensions == []


def test_missing_triggers_defaults_to_empty(tmp_path):
    """Backwards compatibility: a card without `triggers` block still loads,
    triggers defaults to empty lists. No false push from legacy cards."""
    import json
    (tmp_path / "legacy.json").write_text(json.dumps({
        "name": "legacy", "description": "no triggers block",
        "url": "x", "version": "0", "capabilities": {},
        "default_input_modes": [], "default_output_modes": [],
        "skills": [{"id": "x", "name": "x", "description": "x",
                    "tags": ["t"], "examples": ["e"]}],
    }))
    cards = load_cards(tmp_path)
    assert cards[0].triggers.extensions == []
    assert cards[0].triggers.skills == []


def test_triggers_block_is_validated_lists(tmp_path):
    """If `triggers` is present, extensions/skills are coerced to lists."""
    import json
    (tmp_path / "x.json").write_text(json.dumps({
        "name": "x", "description": "d",
        "url": "x", "version": "0", "capabilities": {},
        "default_input_modes": [], "default_output_modes": [],
        "skills": [{"id": "x", "name": "x", "description": "x",
                    "tags": ["t"], "examples": ["e"]}],
        "triggers": {"extensions": [".tex", ".bib"], "skills": ["draft"]},
    }))
    cards = load_cards(tmp_path)
    assert cards[0].triggers.extensions == [".tex", ".bib"]
    assert cards[0].triggers.skills == ["draft"]
