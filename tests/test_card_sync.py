"""Local-developer drift gate: compares cards/*.json against the live sibling
oh-my-* repos on disk. Skips cleanly wherever a sibling isn't cloned locally --
including every CI clean runner, where NONE of the siblings exist. This is
NOT a CI-enforced gate; it only has teeth on a machine with the siblings
cloned next to oh-my-heroacademia (the maintainer's dev machine).

Caveat: this compares against whatever the local sibling clone currently has
on disk. A stale clone (behind origin/main) can produce a false pass (drift
already fixed upstream) or false fail (local ahead of what's released) --
`git -C ~/<sibling> pull` first if a result looks surprising. Not automated
here: a test suite shouldn't make network calls.
"""
import json
from pathlib import Path

import pytest

from omha.registry import load_cards

CARDS_DIR = Path(__file__).parent.parent / "cards"
SIBLINGS_ROOT = Path.home()

# Installed via plugin marketplace, not a local ~/oh-my-* clone. Their card
# `version` is an internal routing-lane version, unrelated to the installed
# package version (checked 2026-07-19: card said "0.2.0", installed cache
# showed oh-my-claudecode 4.15.x / superpowers 6.1.1). No meaningful sibling
# to diff against. (superpowers.json needs no entry here -- its card `name` is
# "superpowers", which doesn't match the "oh-my-" prefix filter below.)
THIRD_PARTY_CARDS = {"oh-my-claudecode"}

# Cards that deliberately curate a subset of the sibling's skills[] into
# triggers.skills, rather than fully mirroring it (curation is a documented,
# legitimate choice per omha's own 0.5.0 CHANGELOG semantics for this field --
# see design doc Problem section). Version sync is still checked for these;
# only the skill-set equality assertion is skipped. Empty today -- omp/oms/
# omx/omd all currently choose full-mirror as their own policy (per the
# backlog spec this test implements). Add an entry here, with a comment
# citing where that card's owner documented the curation choice, the moment
# a domain card opts for a curated subset.
CURATED_SKILL_CARDS = set()


def _synced_cards():
    cards = load_cards(CARDS_DIR)
    return [c for c in cards if c.name.startswith("oh-my-") and c.name not in THIRD_PARTY_CARDS]


def _skill_ids(plugin_skills):
    """['./skills/omp-init/', ...] -> {'omp-init', ...}"""
    return {Path(s.rstrip("/")).name for s in plugin_skills}


@pytest.mark.parametrize("card", _synced_cards(), ids=lambda c: c.name)
def test_card_matches_sibling_repo(card):
    manifest_path = SIBLINGS_ROOT / card.name / ".claude-plugin" / "plugin.json"
    if not manifest_path.is_file():
        pytest.skip(
            f"{card.name}: no local clone at {manifest_path} -- expected on CI "
            "clean runners and on a dev machine that hasn't cloned this sibling; "
            "this is a local-developer drift gate, not a CI-enforced one"
        )

    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as e:
        pytest.fail(f"card-sync: {manifest_path} is not valid JSON ({e})")
    for key in ("version", "skills"):
        if key not in manifest:
            pytest.fail(f"card-sync: {manifest_path} is missing required key {key!r}")

    assert card.version == manifest["version"], (
        f"card-sync drift: cards/*.json for {card.name!r} says version="
        f"{card.version!r}, but the live repo at {manifest_path.parent.parent} "
        f"is version={manifest['version']!r} -- bump the card to match"
    )

    if card.name in CURATED_SKILL_CARDS:
        return  # skill-set equality intentionally not required -- curated by design

    sibling_skills = _skill_ids(manifest["skills"])
    card_skills = set(card.triggers.skills)
    missing_from_card = sorted(sibling_skills - card_skills)
    stale_in_card = sorted(card_skills - sibling_skills)
    assert not missing_from_card and not stale_in_card, (
        f"card-sync drift in {card.name}'s triggers.skills: "
        f"missing (in repo, not in card)={missing_from_card}, "
        f"stale (in card, not in repo)={stale_in_card}"
    )
