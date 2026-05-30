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
        "레인만 정하라 — 레인 안 스킬 콕집기는 해당 plugin 이 한다.\n\n"
        f"{body}\n\n"
        "폴백 캐스케이드 (위에서부터, 맞는 게 없으면 다음):\n"
        "· 1순위 — 위 하네스 레인(작업방식: SP/OMC) 중 적합한 것.\n"
        "· 2순위 — 적합 레인 없음 → 설치된 도메인 스킬(문서=OMD, 슬라이드·이미지 등). 이건 레인이 아니라 도메인 처리기.\n"
        "· 3순위 — 그것도 없음 → handle-directly(직접 수행).\n\n"
        "재라우팅 의무: 2순위 도메인 스킬 안에서 작업 중이라도, 본질적으로 작업방식\n"
        "레인(SP/OMC)에 속하는 무거운 하위작업(여러 출처 병렬 조사·깊은 리서치·왜인지\n"
        "분석·test-first 코드)을 만나면 그 자리에서 레인 판정을 다시 하라. 단 3-4줄짜리\n"
        "단순 확인은 직접 처리(과흡인 금지). citation-bound 문서(논문)의 자료 조사는\n"
        "하되 OMC 병렬은 금지.\n\n"
        "자료조사 적극 위임(사용자 지침): 무거운 문헌 조사·외부 repo/라이브러리 조사·\n"
        "기술 비교(best practice, X vs Y, 최신 패턴)는 직접 단발 검색으로 때우지 말고\n"
        "OMC research 스킬을 적극 중용하라 — 외부로 나가는 조사(웹·공식문서·GitHub repo\n"
        "탐색)는 oh-my-claudecode:external-context(facet 분해→병렬 검색→URL 인용),\n"
        "주어진 대상의 깊은 분석(이 코드베이스/이 repo가 어떻게 동작하나)은\n"
        "oh-my-claudecode:sciomc. 단 3-4줄 단순 lookup은 직접(과흡인 금지),\n"
        "citation-bound 논문 자료조사는 OMC 병렬 금지(위 가드 그대로).\n\n"
        "판정을 응답 맨 앞에 이 한 줄로 먼저 출력하라(매 턴, 누락 금지):\n"
        "ROUTE → <oh-my-claudecode|superpowers|domain-skill|handle-directly> · <한 줄 근거>\n"
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
