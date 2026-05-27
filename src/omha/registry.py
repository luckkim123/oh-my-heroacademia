"""Declarative card registry: every cards/*.json becomes an A2A AgentCard.
Adding a harness = drop one JSON file here. Core never changes (design extensibility rule)."""
import json
from pathlib import Path
from a2a.types import AgentCard


def load_cards(cards_dir: Path) -> list[AgentCard]:
    cards = []
    for path in sorted(Path(cards_dir).glob("*.json")):
        data = json.loads(path.read_text())
        cards.append(AgentCard.model_validate(data))
    return cards
