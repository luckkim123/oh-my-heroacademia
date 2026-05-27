from fastapi.testclient import TestClient
from omha.server import create_app

client = TestClient(create_app())

def test_lists_all_harness_cards():
    r = client.get("/harnesses")
    assert r.status_code == 200
    names = {h["name"] for h in r.json()}
    assert {"superpowers", "oh-my-claudecode", "oh-my-docs"} <= names

def test_per_harness_well_known_card():
    r = client.get("/harness/superpowers/.well-known/agent-card.json")
    assert r.status_code == 200
    card = r.json()
    assert card["name"] == "superpowers"
    assert "skills" in card

def test_route_endpoint_returns_verdict():
    r = client.post("/route", json={"request": "write this with tests first"})
    assert r.status_code == 200
    body = r.json()
    assert body["harness"] == "superpowers"
    assert body["original_request"] == "write this with tests first"  # verbatim

def test_unknown_harness_404():
    r = client.get("/harness/nope/.well-known/agent-card.json")
    assert r.status_code == 404
