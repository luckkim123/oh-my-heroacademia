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
    """Inject the lane-routing checkpoint.

    Cards split into two kinds by their lane_type field:
      · domain     (oms/omd — WHAT product: paper .tex/.bib, document .pptx…)
      · work-style (omc/sp/omx — HOW you work: throughput, discipline, experiments)

    The cascade is DOMAIN-FIRST (2026-06-02 design): when the work product is an
    unambiguous domain, route into that domain harness BEFORE the work-style
    lanes — so paper work ALWAYS enters oms, document work enters omd. Only when
    no domain matches do the work-style lanes apply. This replaces the older
    "SP/OMC-only, domains are 2nd-tier installed skills" cascade.
    """
    domain_lanes, work_lanes = [], []
    verdict_names = []
    for path in sorted(Path(cards_dir).glob("*.json")):
        d = json.loads(path.read_text())
        line = f"- {d['name']}: {d['description']}"
        if d.get("lane_type") == "domain":
            domain_lanes.append(line)
        else:
            work_lanes.append(line)
        verdict_names.append(d["name"])
    domain_body = "\n".join(domain_lanes) if domain_lanes else "  (없음)"
    work_body = "\n".join(work_lanes)
    verdict_enum = "|".join(verdict_names)
    return (
        "<omha-routing>\n"
        "3+ 액션/복수파일 요청이면, 아래 하네스 카드로 어느 레인인지 한 줄 판정·선언하라.\n"
        "레인만 정하라 — 레인 안 스킬 콕집기는 해당 plugin 이 한다.\n\n"
        "■ 도메인 하네스 (WHAT — 만드는 산출물이 정함. 명확하면 *먼저* 여기로):\n"
        f"{domain_body}\n\n"
        "■ 작업방식 레인 (HOW — 일하는 방식이 정함):\n"
        f"{work_body}\n\n"
        "판정 캐스케이드 (도메인 우선 — 위에서부터):\n"
        "· 1순위 — 산출물 도메인이 명확한가? (논문 .tex/.bib → oh-my-scholar, 문서\n"
        "  .pptx/.docx → oh-my-docs). 명확하면 무조건 그 도메인 하네스로 진입한다.\n"
        "  특히 논문 작업은 *반드시* oh-my-scholar 로 — 직접 수행하거나 OMC 병렬로\n"
        "  때우지 말 것(citation 무결성 가드가 oms 안에만 있다).\n"
        "· 2순위 — 도메인이 안 잡히면 작업방식 레인(SP/OMC/OMX) 중 적합한 것.\n"
        "· 3순위 — 그것도 없음 → handle-directly(직접 수행).\n\n"
        "재라우팅 의무: 도메인 하네스 안에서 작업 중이라도, 본질적으로 작업방식\n"
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
        f"ROUTE → <{verdict_enum}|handle-directly> · <한 줄 근거>\n"
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
