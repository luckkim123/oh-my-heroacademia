from omha.registry import load_cards


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
