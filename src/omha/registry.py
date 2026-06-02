"""Declarative card registry: every cards/*.json becomes an AgentCard.
Adding a harness = drop one JSON file here. Core never changes (design extensibility rule).

Stdlib only — no a2a-sdk runtime dependency. The hook (route_emit.py) already
reads cards with json.loads directly; this module is the typed validation layer
used by tests and any future tooling. It mirrors the subset of the A2A AgentCard
shape that omha actually depends on (name / description / skills[].tags|examples),
validated with dataclasses so omha stays dependency-free and runs on Python 3.9+.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

# AgentCard required fields (A2A shape subset omha relies on).
_CARD_REQUIRED = (
    "name", "description", "url", "version", "capabilities",
    "default_input_modes", "default_output_modes", "skills",
)
_SKILL_REQUIRED = ("id", "name", "description", "tags", "examples")


@dataclass
class AgentSkill:
    id: str
    name: str
    description: str
    tags: list
    examples: list

    @classmethod
    def from_dict(cls, data: dict) -> "AgentSkill":
        missing = [k for k in _SKILL_REQUIRED if k not in data]
        if missing:
            raise ValueError(f"skill missing required field(s): {missing}")
        return cls(
            id=data["id"], name=data["name"], description=data["description"],
            tags=data["tags"], examples=data["examples"],
        )


@dataclass
class AgentTriggers:
    """Optional push-routing signals consumed by cross_lane_emit.py PreToolUse hook.

    Cards declare what concrete tool-call signals (file extensions, skill names)
    map to their lane. The hook reads these — extension/skill lookup is the
    objective channel that complements the model's pull-side judgment.
    """
    extensions: list = field(default_factory=list)
    skills: list = field(default_factory=list)


@dataclass
class AgentCard:
    name: str
    description: str
    url: str
    version: str
    capabilities: dict
    default_input_modes: list
    default_output_modes: list
    skills: list = field(default_factory=list)
    triggers: AgentTriggers = field(default_factory=AgentTriggers)
    # "work-style" (omc/sp/omx — HOW you work) or "domain" (oms/omd — WHAT
    # product). The route cascade orders domain BEFORE work-style so an
    # unambiguous domain (paper .tex / document .pptx) always enters its own
    # harness first. Defaults to "work-style" for backward compatibility with
    # any card that predates this field. (2026-06-02 domain-first design.)
    lane_type: str = "work-style"

    @classmethod
    def model_validate(cls, data: dict) -> "AgentCard":
        missing = [k for k in _CARD_REQUIRED if k not in data]
        if missing:
            raise ValueError(f"card missing required field(s): {missing}")
        t = data.get("triggers", {})
        return cls(
            name=data["name"], description=data["description"], url=data["url"],
            version=data["version"], capabilities=data["capabilities"],
            default_input_modes=data["default_input_modes"],
            default_output_modes=data["default_output_modes"],
            skills=[AgentSkill.from_dict(s) for s in data["skills"]],
            triggers=AgentTriggers(
                extensions=list(t.get("extensions", [])),
                skills=list(t.get("skills", [])),
            ),
            lane_type=data.get("lane_type", "work-style"),
        )


def load_cards(cards_dir: Path) -> list:
    cards = []
    for path in sorted(Path(cards_dir).glob("*.json")):
        data = json.loads(path.read_text())
        cards.append(AgentCard.model_validate(data))
    return cards
