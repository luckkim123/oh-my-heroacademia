from pathlib import Path
from omha.registry import load_cards
from omha.router import route

CARDS = load_cards(Path(__file__).parent.parent / "cards")

def test_tdd_request_routes_to_superpowers():
    v = route("write this feature with tests first, correctness matters", CARDS)
    assert v.harness == "superpowers"
    assert v.original_request  # request preserved verbatim (no paraphrase)

def test_bulk_edit_routes_to_omc():
    v = route("rename this symbol across 20 files in parallel", CARDS)
    assert v.harness == "oh-my-claudecode"

def test_pptx_request_routes_to_omd():
    v = route("make a slide deck / 발표자료 만들어줘", CARDS)
    assert v.harness == "oh-my-docs"

def test_verdict_includes_reason():
    v = route("loop until tests pass", CARDS)
    assert v.reason  # non-empty human-readable why

def test_short_tag_does_not_substring_misfire():
    # 'spec' tag must NOT match inside 'inspect'; this request has no real signal
    # so it should fall to the no-signal default, not be dragged to superpowers by a substring.
    v = route("inspect the cluttered area", CARDS)
    assert v.reason  # has a reason either way
    # the point: 'spec' did not spuriously fire — scores for superpowers stay 0 here
    assert v.scores.get("superpowers", 0) == 0
