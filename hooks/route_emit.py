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

    Cards split into three kinds by their lane_type field:
      · governance (omp — WHERE files belong / does the tree obey its rules)
      · domain     (oms/omd — WHAT product: paper .tex/.bib, document .pptx…)
      · work-style (omc/sp/omx — HOW you work: throughput, discipline, experiments)

    The cascade is GOVERNANCE-FIRST, then DOMAIN, then work-style (2026-06-05
    design). Governance is an axis ORTHOGONAL to the content domains: the same
    .pptx is omd when you author its content but omp when you ask whether it sits
    in the right folder. So structure/placement/rule work is judged BEFORE the
    content domains (else it falls through to handle-directly — the bug this
    fixes), domains are judged before the work-style lanes (paper work ALWAYS
    enters oms, document work enters omd), and only when none match do the
    work-style lanes apply.
    """
    governance_lanes, domain_lanes, work_lanes = [], [], []
    verdict_names = []
    for path in sorted(Path(cards_dir).glob("*.json")):
        d = json.loads(path.read_text())
        line = f"- {d['name']}: {d['description']}"
        lane_type = d.get("lane_type")
        if lane_type == "governance":
            governance_lanes.append(line)
        elif lane_type == "domain":
            domain_lanes.append(line)
        else:
            work_lanes.append(line)
        verdict_names.append(d["name"])
    governance_body = "\n".join(governance_lanes) if governance_lanes else "  (없음)"
    domain_body = "\n".join(domain_lanes) if domain_lanes else "  (없음)"
    work_body = "\n".join(work_lanes)
    verdict_enum = "|".join(verdict_names)
    return (
        "<omha-routing>\n"
        "3+ 액션/복수파일 요청이면, 아래 하네스 카드로 어느 레인인지 한 줄 판정·선언하라.\n"
        "레인만 정하라 — 레인 안 스킬 콕집기는 해당 plugin 이 한다.\n\n"
        "■ 거버넌스 하네스 (WHERE — 파일이 어디 속하나·트리가 규칙 지키나. 산출물 축과 직교):\n"
        f"{governance_body}\n\n"
        "■ 도메인 하네스 (WHAT — 만드는 산출물이 정함. 명확하면 *먼저* 여기로):\n"
        f"{domain_body}\n\n"
        "■ 작업방식 레인 (HOW — 일하는 방식이 정함):\n"
        f"{work_body}\n\n"
        "판정 캐스케이드 (거버넌스 → 도메인 → 작업방식, 위에서부터):\n"
        "· 0순위 — 구조/배치/규칙 문제인가? (파일이 제자리야? 재배치해? 명명·dataset·\n"
        "  .omp 규칙?) 그렇다면 oh-my-project. 산출물 축과 직교하므로 *가장 먼저* 본다 —\n"
        "  같은 .pptx라도 '내용을 만들면' omd, '제자리에 있나'면 omp. 구조 작업이\n"
        "  도메인·작업방식으로 새서 handle-directly 로 떨어지는 것을 막는 단계.\n"
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
        "산출물-수정 재라우팅(handle-directly 시작분도 적용): 어떤 레인으로 시작했든\n"
        "— handle-directly 로 질문에 답하던 중이라도 — 하네스가 소유한 *산출물 파일*\n"
        "(exp-analyze 의 report.md/.ko.md, omd 의 .pptx/.docx, oms 의 .tex/.bib)을\n"
        "*수정*하는 단계로 넘어가는 순간 레인을 재판정하라. 그 파일들의 양식·검증\n"
        "게이트는 해당 하네스 스킬을 *경유할 때만* 발동하므로, Edit/Write 로 직접\n"
        "고치면 게이트가 통째로 우회된다. report.md 수정 → oh-my-experiments(exp-analyze\n"
        "재분석), 문서 수정 → oh-my-docs, 논문 수정 → oh-my-scholar 로 들어가 그 스킬의\n"
        "쓰기 경로로 고친다. '질문 답하다 그 흐름으로 산출물을 직접 손보는' 경로가\n"
        "바로 이 의무가 막는 것 — 산출물을 직접 Edit 하기 전에 다시 ROUTE 를 찍어라.\n\n"
        "자료조사 적극 위임(사용자 지침): 무거운 문헌 조사·외부 repo/라이브러리 조사·\n"
        "기술 비교(best practice, X vs Y, 최신 패턴)는 직접 단발 검색으로 때우지 말고\n"
        "OMC research 스킬을 적극 중용하라 — 외부로 나가는 조사(웹·공식문서·GitHub repo\n"
        "탐색)는 oh-my-claudecode:external-context(facet 분해→병렬 검색→URL 인용),\n"
        "주어진 대상의 깊은 분석(이 코드베이스/이 repo가 어떻게 동작하나)은\n"
        "oh-my-claudecode:sciomc. 단 3-4줄 단순 lookup은 직접(과흡인 금지),\n"
        "citation-bound 논문 자료조사는 OMC 병렬 금지(위 가드 그대로).\n\n"
        "요구사항 분석 선행(ANALYZE-then-ROUTE): 요청이 3+ 액션/복수파일이거나\n"
        "모호하면, ROUTE 줄보다 *먼저* 아래 ANALYZE 블록을 출력해 요구사항을\n"
        "분해하라 — routing·작업은 이 분석을 토대로 한다(잘못 이해해 되돌리는\n"
        "토큰 낭비 방지). 단순·명확한 1~2액션 요청이면 ANALYZE 생략(분석 비용이\n"
        "이득을 넘는 과흡인 금지) — 이 경우 곧장 ROUTE 만 출력한다.\n"
        "ANALYZE 를 띄울 때 형식 — GFM 인용 블록(blockquote)으로 출력해 본문과\n"
        "시각적으로 분리하라. 각 줄을 '> ' 로 시작하고, 첫 줄은 볼드 헤더, 4개\n"
        "필드는 '> - ' 불릿 + 볼드 라벨로 낸다(아래를 그대로 따르되 <…> 만 채움):\n"
        "> **ANALYZE**\n"
        "> - **목적**: <이 요청으로 달성하려는 것 한 줄>\n"
        "> - **핵심 요구**: <반드시 만족할 것 — 쉼표로 나열>\n"
        "> - **제약**: <지켜야 할 한계·보존 범위 / 없으면 '특이사항 없음'>\n"
        "> - **모호한 점**: <해석이 갈리는 지점 / 없으면 '없음'>\n\n"
        "(middle-dot '·' 나 평문 들여쓰기로 내지 말 것 — 그러면 마크다운이\n"
        "리스트로 인식 못 해 라벨이 한 덩어리로 뭉친다. 반드시 '> ' 인용 +\n"
        "'-' 불릿 + 볼드 라벨.) 모호한 점이 '없음' 이 아니면, ROUTE·작업으로\n"
        "넘어가지 말고 그 지점을 먼저 사용자에게 확인하라.\n\n"
        "출력 순서(매 턴, 누락 금지): 응답의 가장 처음에, 게이트에 해당하면\n"
        "ANALYZE 블록을 *먼저* 통째로 내고, 그 *바로 아래* 줄에 ROUTE 를 낸다 —\n"
        "ANALYZE 가 ROUTE 보다 위. (다른 라우팅 블록이 'ROUTE 를 맨 앞에' 라고\n"
        "말하더라도, 게이트 해당 시엔 ANALYZE 가 그 맨 앞 자리를 차지하고 ROUTE 는\n"
        "바로 다음 줄이다 — 이 순서가 그 지시들보다 우선한다.) 게이트에 해당하지\n"
        "않으면 ANALYZE 없이 ROUTE 만 응답 맨 앞 줄에 낸다.\n\n"
        "ROUTE 도 ANALYZE 와 같은 GFM 인용 블록으로 낸다(평문·middle-dot 금지) —\n"
        "'> **ROUTE →** … ' 한 줄. ANALYZE 와 같이 낼 때는 ANALYZE 인용\n"
        "블록 끝에 빈 인용 줄('>') 하나로 띄우고 그 아래에 ROUTE 인용 줄을 붙여\n"
        "둘이 하나의 인용 박스로 묶이게 하라(본문과 한눈에 분리됨). 형식:\n\n"
        "(게이트 해당 시 — ANALYZE+ROUTE 한 인용 박스)\n"
        "> **ANALYZE**\n"
        "> - **목적**: …\n"
        "> - **핵심 요구**: …\n"
        "> - **제약**: …\n"
        "> - **모호한 점**: …\n"
        ">\n"
        f"> **ROUTE →** <{verdict_enum}|handle-directly> · <한 줄 근거>\n\n"
        "(게이트 비해당 시 — ROUTE 만)\n"
        f"> **ROUTE →** <{verdict_enum}|handle-directly> · <한 줄 근거>\n"
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
