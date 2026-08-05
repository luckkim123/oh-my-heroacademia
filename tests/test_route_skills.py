"""route-<lane> declaration skills: cards ↔ skills/ ↔ plugin.json stay in sync.

The lane verdict is declared by CALLING a `route-<lane>` skill rather than by
writing a ROUTE line into the reply. That makes three artifacts co-dependent:

  cards/*.json      route_skill: which skill declares this lane   (SSOT)
  skills/<slug>/    the skill itself, or the call cannot be made
  plugin.json       the skills list Claude Code actually loads

Any one of them drifting silently breaks routing for that lane — the model would
call a skill that does not exist, or the gate would never see a declaration. These
tests are the drift alarm: add a card, and they fail until the skill exists and is
registered.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARDS = sorted((ROOT / "cards").glob("*.json"))

# The one lane with no card: "no lane at all" is a verdict, not a harness.
HANDLE_DIRECTLY_SKILL = "route-direct"


def _cards():
    return [json.loads(p.read_text(encoding="utf-8")) for p in CARDS]


def _manifest():
    return json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))


def test_every_card_declares_a_route_skill():
    missing = [d.get("name") for d in _cards() if not d.get("route_skill")]
    assert missing == [], f"cards without route_skill: {missing}"


def test_route_skill_slugs_are_unique():
    slugs = [d["route_skill"] for d in _cards()]
    assert len(slugs) == len(set(slugs)), f"duplicate route_skill: {slugs}"


def test_route_skill_naming_convention():
    """The gate matches `route-<lane>`; a slug outside that shape is invisible to it."""
    for d in _cards():
        slug = d["route_skill"]
        assert slug.startswith("route-") and slug.islower(), f"bad slug: {slug}"


def test_every_declared_skill_exists_on_disk():
    for slug in [d["route_skill"] for d in _cards()] + [HANDLE_DIRECTLY_SKILL]:
        p = ROOT / "skills" / slug / "SKILL.md"
        assert p.is_file(), f"card points at a skill that does not exist: {p}"


def test_every_route_skill_is_registered_in_the_manifest():
    listed = set(_manifest().get("skills", []))
    for slug in [d["route_skill"] for d in _cards()] + [HANDLE_DIRECTLY_SKILL]:
        assert f"./skills/{slug}/" in listed, f"{slug} missing from plugin.json skills"


def test_handle_directly_skill_exists_even_though_it_has_no_card():
    assert (ROOT / "skills" / HANDLE_DIRECTLY_SKILL / "SKILL.md").is_file()


def test_skill_frontmatter_name_matches_its_directory():
    for d in (ROOT / "skills").iterdir():
        if not d.is_dir():
            continue
        body = (d / "SKILL.md").read_text(encoding="utf-8")
        assert body.startswith("---\n"), f"{d.name}: no frontmatter"
        fm = body.split("---\n", 2)[1]
        assert f"name: {d.name}\n" in fm, f"{d.name}: frontmatter name mismatch"


def test_gate_would_accept_every_declared_skill():
    """End-to-end tie-in: each slug must satisfy route_guard's detection regex."""
    import sys
    sys.path.insert(0, str(ROOT / "hooks"))
    import route_guard as rg

    for slug in [d["route_skill"] for d in _cards()] + [HANDLE_DIRECTLY_SKILL]:
        window = f"ROUTE → oh-my-heroacademia:{slug}"
        assert rg.has_route_line(window), f"gate would not accept {slug}"
        assert rg._ROUTE_SKILL_RE.search(f"oh-my-heroacademia:{slug}"), slug
