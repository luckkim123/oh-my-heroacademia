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


def test_omc_card_declares_deep_interview_trigger():
    """의중 미결정 요청의 목적지(캐스케이드 2.5순위)가 카드 스키마에도 선언돼야 한다.
    2026-08-05 결함: route_emit 는 description 만 주입하므로 deep-interview 는 어느
    경로로도 omha 에서 도달 불가였다 — 카드 description 에도 triggers 에도 없어서,
    리터럴 'deep interview' 키워드 매칭으로만 발동했다. 캐스케이드가 이 스킬을
    이름으로 지목하는 이상 카드도 같은 사실을 선언해야 둘이 따로 놀지 않는다."""
    cards = {c.name: c for c in load_cards(CARDS_DIR)}
    assert "deep-interview" in cards["oh-my-claudecode"].triggers.skills


def test_undecided_goal_exception_is_in_both_work_style_descriptions():
    """`description` 은 route_emit 이 유일하게 주입하는 필드다. 목표 미결정 예외가
    한쪽 카드에만 있으면 같은 블록 안에서 두 카드가 서로를 부정한다 — sp 는 '이 경우
    brainstorming 진입 허용', omc 는 'sp 진입은 오직 3개 게이트뿐'. 두 카드가 같은
    예외를 선언해야 모순이 안 생기고, 되돌리면 이 테스트가 실패한다."""
    cards = {c.name: c for c in load_cards(CARDS_DIR)}
    assert "no direction yet" in cards["superpowers"].description
    assert "non-gate exception" in cards["oh-my-claudecode"].description


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
