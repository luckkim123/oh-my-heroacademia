"""omha A2A HTTP server (stage-1 판정형).
- /harnesses                                   list registered cards
- /harness/{name}/.well-known/agent-card.json  A2A discovery per harness
- /route   (POST {request})                    판정 verdict (no forward yet)

Multi-card by design: the official a2a-sdk app wrapper publishes a single
agent card, but omha is a registry of many harnesses, so we mount the
discovery routes ourselves and reuse AgentCard only as the typed schema."""
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from omha.registry import load_cards
from omha.router import route as route_request

CARDS_DIR = Path(__file__).parent.parent.parent / "cards"


class RouteIn(BaseModel):
    request: str


def create_app(cards_dir: Path = CARDS_DIR) -> FastAPI:
    cards = load_cards(cards_dir)
    by_name = {c.name: c for c in cards}
    app = FastAPI(title="omha", description="meta-coordinator (stage-1 판정형)")

    @app.get("/harnesses")
    def list_harnesses():
        return [{"name": c.name, "description": c.description} for c in cards]

    @app.get("/harness/{name}/.well-known/agent-card.json")
    def agent_card(name: str):
        card = by_name.get(name)
        if card is None:
            raise HTTPException(status_code=404, detail=f"no harness '{name}'")
        return card.model_dump(mode="json", exclude_none=True, by_alias=True)

    @app.post("/route")
    def do_route(body: RouteIn):
        v = route_request(body.request, cards)
        return {
            "harness": v.harness,
            "reason": v.reason,
            "original_request": v.original_request,  # verbatim, never paraphrased
            "scores": v.scores,
        }

    return app


app = create_app()


def main():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8973)


if __name__ == "__main__":
    main()
