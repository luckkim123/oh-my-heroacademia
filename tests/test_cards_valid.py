from pathlib import Path
from omha.registry import load_cards

CARDS_DIR = Path(__file__).parent.parent / "cards"

def test_three_cards_present():
    names = {c.name for c in load_cards(CARDS_DIR)}
    assert {"superpowers", "oh-my-claudecode", "oh-my-docs"} <= names

def test_every_card_has_routing_signal():
    for card in load_cards(CARDS_DIR):
        assert card.skills, f"{card.name} has no skills"
        for skill in card.skills:
            assert skill.tags, f"{card.name}/{skill.name} has no tags"
            assert skill.examples, f"{card.name}/{skill.name} has no examples"
