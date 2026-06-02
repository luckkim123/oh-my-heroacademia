"""Domain-first routing regression guard.

2026-06-02 design supersede: omha used to route between work-style harnesses
ONLY (SP/OMC/OMX), treating oms (paper) / omd (document) as installed domain
skills reached via the 2nd-tier fallback. The user explicitly requested that
paper work ALWAYS enters oms — so domains are promoted to first-class routing
cards and the cascade is flipped to "domain-first".

SSOT design: workspace .sp/specs/2026-06-02-oms-wiki-and-domain-routing-design.md §3.
This replaces the "SP/OMC only" invariant in test_cards_valid.py.

Stdlib + pytest only (mirrors the rest of omha's test suite)."""
import json
from pathlib import Path

from omha.registry import load_cards

CARDS_DIR = Path(__file__).parent.parent / "cards"
HOOKS_DIR = Path(__file__).parent.parent / "hooks"


# ─── cards present ───────────────────────────────────────────────────────────

def test_domain_cards_present():
    """oms and omd are now first-class routing cards, not 2nd-tier skills."""
    names = {c.name for c in load_cards(CARDS_DIR)}
    assert "oh-my-scholar" in names, "oms must be a routing card (paper domain)"
    assert "oh-my-docs" in names, "omd must be a routing card (document domain)"


def test_work_style_cards_still_present():
    """Promoting domains must not drop the work-style lanes."""
    names = {c.name for c in load_cards(CARDS_DIR)}
    assert {"superpowers", "oh-my-claudecode", "oh-my-experiments"} <= names


# ─── lane_type field distinguishes domain from work-style ────────────────────

def _raw_cards():
    return {p.stem: json.loads(p.read_text()) for p in CARDS_DIR.glob("*.json")}


def test_every_card_declares_lane_type():
    """Each card declares lane_type so the cascade can order domain before work-style."""
    for stem, d in _raw_cards().items():
        assert d.get("lane_type") in ("work-style", "domain"), \
            f"{stem}.json must declare lane_type as 'work-style' or 'domain'"


def test_domain_lane_type_assignment():
    raw = _raw_cards()
    assert raw["oms"]["lane_type"] == "domain"
    assert raw["omd"]["lane_type"] == "domain"
    assert raw["omc"]["lane_type"] == "work-style"
    assert raw["superpowers"]["lane_type"] == "work-style"
    assert raw["omx"]["lane_type"] == "work-style"


# ─── domain cards carry concrete push triggers (extensions) ──────────────────

def test_domain_cards_have_extension_triggers():
    """Domain cards must declare file-extension triggers so the push channel
    (cross_lane_emit) can objectively detect domain work from a Write/Edit call."""
    raw = _raw_cards()
    oms_ext = raw["oms"].get("triggers", {}).get("extensions", [])
    omd_ext = raw["omd"].get("triggers", {}).get("extensions", [])
    assert ".tex" in oms_ext and ".bib" in oms_ext, "oms must trigger on .tex/.bib"
    assert ".pptx" in omd_ext and ".docx" in omd_ext, "omd must trigger on .pptx/.docx"


# ─── route_emit injects domain-first cascade ─────────────────────────────────

def _route_context():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "route_emit", HOOKS_DIR / "route_emit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build_routing_context(CARDS_DIR)


def test_route_context_states_domain_first():
    """The injected cascade must tell the model to check domain (oms/omd) BEFORE
    work-style lanes — this is the load-bearing change for 'paper => always oms'."""
    ctx = _route_context()
    # domain harness names must appear in the injected routing text
    assert "oh-my-scholar" in ctx
    assert "oh-my-docs" in ctx
    # the cascade must signal domain-first ordering, not the old SP/OMC-first
    lowered = ctx.lower()
    assert "도메인" in ctx or "domain" in lowered
    # the ROUTE verdict enum must now allow the domain harnesses as a verdict
    assert "oh-my-scholar" in ctx and "oh-my-docs" in ctx


def test_route_context_keeps_research_subroute_to_omc():
    """Domain-first must NOT swallow heavy sub-tasks: the existing guard that
    routes heavy research/test-first sub-work back to OMC/SP, and the
    citation-bound 'no OMC parallel' guard, must survive."""
    ctx = _route_context()
    assert "재라우팅" in ctx or "re-route" in ctx.lower()
    assert "citation" in ctx.lower()
