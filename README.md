# omha — oh-my-heroacademia

omha is a meta-coordinator that routes an incoming task description to the right harness — superpowers, oh-my-claudecode (OMC), or oh-my-docs (OMD) — by matching it against declarative A2A agent cards. Each harness publishes a card (`cards/<name>.json`) that describes what it handles; omha reads those cards at startup and uses a stage-1 keyword scorer to return a routing verdict.

## Status

MVP: stage-1 판정형 A2A server. omha returns a **verdict** (which harness to use and why) but does not yet forward the request. Forwarding and multi-stage routing are planned for v0.2.

## How to run

```bash
pip install -e .
omha          # boots on 127.0.0.1:8973
```

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/harnesses` | List all registered harness cards |
| GET | `/harness/{name}/.well-known/agent-card.json` | A2A discovery card for a specific harness |
| POST | `/route` | Return a routing verdict for a task description |

**Quick example:**

```bash
# List harnesses
curl http://127.0.0.1:8973/harnesses

# Route a request
curl -s -X POST http://127.0.0.1:8973/route \
  -H "Content-Type: application/json" \
  -d '{"request": "write tests for the new feature and make them pass"}' | python3 -m json.tool
```

## How to add a harness

Drop a new file at `cards/<name>.json` following the A2A AgentCard schema. No core code change required — omha loads all `*.json` files in `cards/` at startup. The `skills[].examples` list in the card drives the keyword router.

## Design doc

`/Users/kimseungmin/Desktop/workspace/00-09_Meta/02_Decisions/2026-05-27-omha-design.md`
