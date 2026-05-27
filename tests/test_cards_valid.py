from pathlib import Path
from omha.registry import load_cards

CARDS_DIR = Path(__file__).parent.parent / "cards"

def test_harness_cards_present():
    # omha routes between work-style harnesses only (SP/OMC). OMD is a document
    # domain tool — it ships via the heroacademia marketplace and is reached as
    # an installed skill, not as an omha routing card. See
    # 2026-05-28-omha-redesign-cards-not-server.md §5 (3-tier cascade).
    names = {c.name for c in load_cards(CARDS_DIR)}
    assert {"superpowers", "oh-my-claudecode"} <= names

def test_every_card_has_routing_signal():
    for card in load_cards(CARDS_DIR):
        assert card.skills, f"{card.name} has no skills"
        for skill in card.skills:
            assert skill.tags, f"{card.name}/{skill.name} has no tags"
            assert skill.examples, f"{card.name}/{skill.name} has no examples"
