"""omha stage-1 UserPromptSubmit hook: read cards/*.json (stdlib only),
inject a lane-routing checkpoint. NO a2a-sdk (runtime dep = 0).

The card knowledge lives in cards/*.json (single source of truth). This hook
only *reads and injects* it — it never embeds the knowledge inline, so there is
no drift (the anti-pattern the legacy claude-settings routing had between
using-omc/SKILL.md and routing-verdict-reminder.py)."""
import json
import sys
from pathlib import Path

CARDS_DIR = Path(__file__).resolve().parent.parent / "cards"


def build_routing_context(cards_dir: Path) -> str:
    lanes = []
    for path in sorted(Path(cards_dir).glob("*.json")):
        d = json.loads(path.read_text())
        lanes.append(f"- {d['name']}: {d['description']}")
    body = "\n".join(lanes)
    return (
        "<omha-routing>\n"
        "3+ 액션/복수파일 요청이면, 아래 하네스 카드로 어느 레인인지 한 줄 판정·선언하라.\n"
        "레인만 정하라 — 레인 안 스킬 콕집기는 해당 plugin 이 한다. "
        "적절한 레인이 없으면 handle-directly(직접 수행).\n\n"
        f"{body}\n"
        "</omha-routing>"
    )


def main() -> int:
    try:
        ctx = build_routing_context(CARDS_DIR)
    except Exception:
        return 0  # 카드 못 읽어도 세션 막지 않음 (fail-open)
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit", "additionalContext": ctx}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
