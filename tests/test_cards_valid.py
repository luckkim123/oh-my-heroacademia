from pathlib import Path
from omha.registry import load_cards

CARDS_DIR = Path(__file__).parent.parent / "cards"

def test_harness_cards_present():
    # 2026-06-02 supersede: omha now routes DOMAIN-FIRST. Domains (oms paper /
    # omd document) are first-class routing cards, not 2nd-tier installed skills
    # — so "paper work always enters oms" is enforced at omha's 1st tier. The
    # old "SP/OMC only" invariant (2026-05-28-omha-redesign-cards-not-server.md
    # §5) is replaced; the full domain-first contract lives in
    # tests/test_domain_first_routing.py and
    # workspace .sp/specs/2026-06-02-oms-wiki-and-domain-routing-design.md §3.
    names = {c.name for c in load_cards(CARDS_DIR)}
    assert {"superpowers", "oh-my-claudecode", "oh-my-experiments"} <= names

def test_every_card_has_routing_signal():
    for card in load_cards(CARDS_DIR):
        assert card.skills, f"{card.name} has no skills"
        for skill in card.skills:
            assert skill.tags, f"{card.name}/{skill.name} has no tags"
            assert skill.examples, f"{card.name}/{skill.name} has no examples"
