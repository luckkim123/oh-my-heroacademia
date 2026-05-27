"""Stage-1 판정형 router: score each card's skills against the request,
return a verdict (harness + reason). No forwarding (that's stage 2).
The request is carried VERBATIM (design forward-original-text rule)."""
from dataclasses import dataclass, field
from a2a.types import AgentCard


@dataclass
class Verdict:
    harness: str
    reason: str
    original_request: str
    scores: dict = field(default_factory=dict)


def _score(request: str, card: AgentCard) -> tuple[int, list[str]]:
    """Count tag/example token hits. Returns (score, matched_terms).
    Deliberately simple keyword overlap — stage-1 is a coarse judge, not an LLM
    classifier. The LLM (Claude reading the verdict) makes the final call."""
    req = request.lower()
    req_tokens = set(req.split())
    score, hits = 0, []
    for skill in card.skills:
        for tag in (skill.tags or []):
            t = tag.lower()
            # ASCII tags: require a whole-token match (avoid 'spec' hitting 'inspect').
            # Non-ASCII tags (Korean 발표자료/문서): substring match (no space tokenization).
            is_ascii = t.isascii()
            matched = (t in req_tokens) if is_ascii else (t in req)
            if matched:
                score += 2
                hits.append(tag)
        for ex in (skill.examples or []):
            ex_words = {w for w in ex.lower().split() if len(w) > 3}
            overlap = ex_words & req_tokens
            if overlap:
                score += len(overlap)
                hits.extend(overlap)
    return score, hits


def route(request: str, cards: list[AgentCard]) -> Verdict:
    scored = {}
    detail = {}
    for card in cards:
        s, hits = _score(request, card)
        scored[card.name] = s
        detail[card.name] = hits
    if not scored or max(scored.values()) == 0:
        # No signal — default to superpowers (discipline) and say so.
        return Verdict(
            harness="superpowers",
            reason="no strong signal matched; defaulting to discipline lane",
            original_request=request,
            scores=scored,
        )
    winner = max(scored, key=lambda n: scored[n])
    return Verdict(
        harness=winner,
        reason=f"matched {detail[winner]} (score {scored[winner]})",
        original_request=request,
        scores=scored,
    )
