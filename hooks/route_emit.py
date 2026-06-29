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
        "매 턴 ROUTE 를 *판정*하되, 출력은 *직전 턴과 레인이 바뀌었을 때만* 낸다\n"
        "(첫 턴은 항상 출력). 직전과 같은 레인이면 ROUTE 줄을 생략한다 — 노이즈를\n"
        "줄이려는 정책이다. 단 생략은 '판정을 건너뛰어도 된다'는 뜻이 절대 아니다:\n"
        "판정은 매 턴 반드시 새로 하고, 그 결과가 직전과 다를 때만 한 줄로 출력한다.\n"
        "3+ 액션/복수파일/모호한 요청이면 ROUTE 위에 ANALYZE 블록을 더 얹는다 —\n"
        "'3+ 액션'은 *ANALYZE 를 추가할* 조건이지 *ROUTE 를 낼* 조건이 아니다.\n"
        "아래 하네스 카드로 어느 레인인지 판정하라. 레인만 정하라 — 레인 안 스킬\n"
        "콕집기는 해당 plugin 이 한다.\n\n"
        "ROUTE 는 채울 출력 슬롯이 아니라 *매 턴 새로 내리는 판정*이다(출력은\n"
        "레인이 바뀔 때만이지만 판정은 매 턴이다 — 둘을 분리하지 말 것). 직전 턴\n"
        "ROUTE 를 관성으로 복사하지 말고 *이번 요청* 기준으로 처음부터 다시 판정하라.\n"
        "그렇게 다시 판정한 결과가 직전과 같으면 출력만 생략하는 것이지, 판정을\n"
        "생략하는 게 아니다. 핵심 함정:\n"
        "topic(주제) 연속성 ≠ routing 연속성. 주제가 직전과 같아도(예: 같은 실험·같은\n"
        "파일) 이번 요청의 *task type* — 요약/설명 vs 검토·심층분석 vs 작성·생성 vs\n"
        "설계 — 이 바뀌면 레인이 바뀐다. '주제가 같으니 라우팅도 같겠지'가 바로 이\n"
        "관성의 정체다. 같은 주제라도 '대화로 답하기'(handle-directly)에서 '코드 근거로\n"
        "깊이 검토·분석하기'(작업방식 레인 + 독립 reviewer)로 넘어가면 재판정 대상이다.\n\n"
        "■ ROUTE 형식 (이 한 줄을 앞에 둬 잘림 방지 — 상세 규칙은 아래):\n"
        "값은 다음 7개 중 *정확히 하나*다(둘을 '·'/슬래시로 잇지 말 것):\n"
        f"  {verdict_enum}|handle-directly\n"
        "형식은 GFM 인용 한 줄(평문·middle-dot 금지):\n"
        f"> **ROUTE →** <{verdict_enum}|handle-directly> · <한 줄 근거>\n"
        "handle-directly = 위임 없이 직접 처리(스킬·에이전트 0). 레인 이름과 같이\n"
        "쓰지 말 것 — 'omc · handle-directly'는 모순(omc=위임, handle-directly=직접).\n\n"
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
        "분석·repo/transcript 정독·test-first 코드)을 만나면 그 자리에서 레인 판정을\n"
        "다시 하라. 특히 그런 하위작업을 `Agent`/`Task`/`Workflow` 로 *위임하기 직전에*\n"
        "멈춰서 레인을 재판정하라 — 외부로 나가는 조사는 external-context, 주어진 대상\n"
        "심층분석은 sciomc 로. raw `Agent` 툴 직접 호출로 OMC research 스킬을 우회하지\n"
        "말 것(아래 산출물-수정 재라우팅의 'Edit 하기 전에' 와 같은 행동-시점 게이트다).\n"
        "단 3-4줄짜리 단순 확인은 직접 처리(과흡인 금지). citation-bound 문서(논문)의\n"
        "자료 조사는 하되 OMC 병렬은 금지.\n\n"
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
        "oh-my-claudecode:sciomc.\n"
        "외부 repo/플러그인/라이브러리를 *조사·분석·도입판단*하는 작업은 액션 수와\n"
        "무관하게(1액션처럼 보여도) OMC 로 라우팅한다 — 대상이 다중 파일로 된 외부\n"
        "산출물이면 실질은 다액션이다. 이때 진입점 하나(README/SKILL.md/메인 파일)만\n"
        "보고 단정 금지: 매니페스트(plugin.json/manifest 등)와 전체 트리를 먼저 확인하라.\n"
        "'단순 lookup' 예외는 *단일 파일·단일 사실 확인*에만 적용 — 여러 파일을 읽거나\n"
        "코드 동작을 해석하거나 구조를 파악해야 하면 lookup 이 아니라 조사이므로 위임한다.\n"
        "단 진짜 3-4줄짜리 단일 사실 lookup 은 직접(과흡인 금지),\n"
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
        "출력 순서(ROUTE 를 낼 때만 — 레인 전환 턴 또는 첫 턴): 응답의 가장\n"
        "처음에, 게이트에 해당하면 ANALYZE 블록을 *먼저* 통째로 내고, 그 *바로\n"
        "아래* 줄에 ROUTE 를 낸다 — ANALYZE 가 ROUTE 보다 위. (다른 라우팅 블록이\n"
        "'ROUTE 를 맨 앞에' 라고 말하더라도, 게이트 해당 시엔 ANALYZE 가 그 맨 앞\n"
        "자리를 차지하고 ROUTE 는 바로 다음 줄이다 — 이 순서가 그 지시들보다\n"
        "우선한다.) 게이트에 해당하지 않으면 ANALYZE 없이 ROUTE 만 응답 맨 앞 줄에\n"
        "낸다. 단 직전 턴과 레인이 같으면 ROUTE 줄 자체를 생략한다(ANALYZE 는\n"
        "게이트 해당 시 레인 변화와 무관하게 낸다 — 요구사항 분해는 출력 노이즈가\n"
        "아니라 작업 정확도용이다).\n\n"
        "닫는 재확인(턴 종료 전): ROUTE 를 (낼 때) 맨 앞에 찍는 건 *행동 전\n"
        "commitment 게이트*다(그 레인 안에서 이번 턴을 한다는 선언). 그래서 낼 때는\n"
        "위치를 끝으로 옮기지 않는다 — 대신 본문을 다 쓴 *뒤* 한 번 대조하라: 내가\n"
        "실제로 한 작업이 이번 판정 레인과 같았나? 깊이 생각해보니(또는 본문 도중\n"
        "무거운 하위작업·산출물 수정으로) 레인이 달라졌다면, 그 사실을 한 줄로\n"
        "명시하고 *갱신된 ROUTE 를 다시 찍어라* — 이 재발행은 직전과 레인이 바뀐\n"
        "것이므로 출력 생략 규칙에 걸리지 않는다(바뀌었으니 낸다). 레인이 직전과\n"
        "그대로인 단순 턴이면 ROUTE 출력도 재발행도 불필요(과흡인 금지) — 판정만\n"
        "조용히 확인하고 넘어간다.\n\n"
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
