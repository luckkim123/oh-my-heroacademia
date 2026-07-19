import pytest

from omha.registry import AgentCard, load_cards


def test_model_validate_raises_on_missing_required_fields():
    """AgentCard.model_validate is the only schema-conformance safety net for the
    card format used in CI (test_cards_valid.py runs load_cards() against the real
    cards/*.json as a de facto gate, but nothing exercises the raise path itself).
    A regression that weakened the check (e.g. swapping to .get(..., default)) would
    silently pass CI with no negative test to catch it."""
    with pytest.raises(ValueError) as exc_info:
        AgentCard.model_validate({"name": "x", "description": "d"})
    msg = str(exc_info.value)
    for field in ("url", "version", "capabilities", "default_input_modes",
                  "default_output_modes", "skills"):
        assert field in msg


def test_load_cards_reads_all_json_in_dir(tmp_path):
    (tmp_path / "foo.json").write_text(
        '{"name":"Foo","description":"d","url":"http://x","version":"1.0.0",'
        '"capabilities":{},"default_input_modes":["text/plain"],'
        '"default_output_modes":["text/plain"],"skills":[]}'
    )
    cards = load_cards(tmp_path)
    assert len(cards) == 1
    assert cards[0].name == "Foo"


def test_load_cards_empty_dir_returns_empty(tmp_path):
    assert load_cards(tmp_path) == []
