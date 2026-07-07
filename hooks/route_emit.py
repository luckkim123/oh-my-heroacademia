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
        "ROUTE 는 출력 슬롯이 아니라 *매 턴 새로 내리는 판정*이다. 매 턴 새로 판정하고\n"
        "매 턴 ROUTE 를 출력한다(레인 변화와 무관 — 하드게이트가 매 턴 ROUTE 를 요구한다).\n"
        "직전 ROUTE 를 관성으로 복사하지 말고 *이번 요청* 기준으로 처음부터 다시\n"
        "판정하라. 레인만 정하라 —\n"
        "레인 안 스킬 콕집기는 해당 plugin 이 한다. 3+ 액션/복수파일/모호한 요청이면\n"
        "ROUTE 위에 ANALYZE 블록을 더 얹는다('3+ 액션'은 *ANALYZE 를 추가할* 조건이지\n"
        "*ROUTE 를 낼* 조건이 아니다 — 상세는 아래 ANALYZE-then-ROUTE).\n"
        "핵심 함정: topic(주제) 연속성 ≠ routing 연속성. 주제가 직전과 같아도(같은 실험·\n"
        "같은 파일) 이번 요청의 *task type* — 요약/설명 vs 검토·심층분석 vs 작성·생성 vs\n"
        "설계 — 이 바뀌면 레인이 바뀐다. '주제가 같으니 라우팅도 같겠지'가 그 관성이다.\n"
        "예: 같은 주제라도 handle-directly(대화로 답)에서 '코드 근거로 깊이 검토·분석'\n"
        "(작업방식 레인 + 독립 reviewer)로 넘어가면 재판정 대상.\n\n"
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
        "재라우팅 의무 (어떤 레인으로 시작했든 — handle-directly 로 답하던 중이라도 —\n"
        "*행동 직전* 다시 ROUTE 를 찍는 행동-시점 게이트):\n"
        "· 위임 직전: 본질적으로 작업방식 레인(SP/OMC)인 무거운 하위작업(여러 출처 병렬\n"
        "  조사·깊은 리서치·왜인지 분석·repo/transcript 정독·test-first 코드)을\n"
        "  `Agent`/`Task`/`Workflow` 로 위임하기 직전에 멈춰 레인을 재판정하라. raw\n"
        "  `Agent` 직접 호출로 OMC research 스킬을 우회하지 말 것.\n"
        "· 산출물 수정 직전: 하네스가 소유한 *산출물 파일*(exp-analyze report.md/.ko.md,\n"
        "  omd .pptx/.docx, oms .tex/.bib)을 *수정*하는 순간 재판정하라. 그 파일들의\n"
        "  양식·검증 게이트는 해당 스킬을 *경유할 때만* 발동하므로 Edit/Write 로 직접\n"
        "  고치면 게이트가 통째로 우회된다 → report.md 는 oh-my-experiments(exp-analyze\n"
        "  재분석), 문서는 oh-my-docs, 논문은 oh-my-scholar 의 쓰기 경로로 고친다.\n"
        "· 리서치 위임(사용자 지침): 무거운 문헌 조사·외부 repo/라이브러리 조사·기술 비교\n"
        "  (best practice, X vs Y, 최신 패턴)는 단발 검색으로 때우지 말고 OMC research 를\n"
        "  적극 중용 — 외부로 나가는 조사(웹·공식문서·GitHub repo)는\n"
        "  oh-my-claudecode:external-context(facet 분해→병렬 검색→URL 인용), 주어진 대상의\n"
        "  깊은 분석(이 코드베이스가 어떻게 동작하나)은 oh-my-claudecode:sciomc.\n"
        "  외부 repo/플러그인/라이브러리를 *조사·분석·도입판단*하는 작업은 액션 수와\n"
        "  무관하게(1액션처럼 보여도) OMC 로 — 다중 파일 외부 산출물이면 실질은 다액션.\n"
        "  진입점 하나(README/SKILL.md)만 보고 단정 말고 매니페스트(plugin.json 등)와\n"
        "  전체 트리를 먼저 확인하라.\n"
        "· 코드 사실 단정 직전: '이 코드가 X 한다/안 한다'를 *단정*하기 직전 멈춰라.\n"
        "  주석·변수명·docstring 이 X 라 말하는 것은 근거가 아니다(이름 vs 구현 불일치).\n"
        "  단정 전 `.claude/rules/03` \"Verify Implementation, Not Name\" 을 실제로 이행\n"
        "  (write-site grep + 레지스트리 대조)한 뒤에만 단정하고, 다파일 추적이면 lookup 이\n"
        "  아니라 조사이므로 OMC(sciomc/explore)로 위임하라. 주석 한 줄 보고 단정하는 것이\n"
        "  이 세션이 반복 오답한 그 사고다.\n"
        "· 예외: 진짜 3-4줄짜리 단일 파일·단일 사실 lookup 은 직접(과흡인 금지). 단\n"
        "  '코드가 이렇게 *동작한다*'는 주장은 lookup 이 아니다 — 한 줄 값 읽기(상수·\n"
        "  경로·버전)만 lookup 이고, 데이터 흐름·배선·'관리/호출/적용되는가'는 여러 파일\n"
        "  추적이 필요한 조사다(아래 '코드 사실 단정' 게이트 적용). 여러 파일을 읽거나\n"
        "  코드 동작을 해석하거나 구조를 파악해야 하면 조사이므로 위임한다.\n"
        "  citation-bound 논문 자료조사는 OMC 병렬 금지.\n\n"
        "요구사항 분석 선행(ANALYZE-then-ROUTE): 요청이 3+ 액션/복수파일이거나 모호하면,\n"
        "ROUTE 줄보다 *먼저* ANALYZE 블록을 출력해 요구사항을 분해하라(잘못 이해해 되돌리는\n"
        "토큰 낭비 방지). 단순·명확한 1~2액션이면 ANALYZE 생략(과흡인 금지), 곧장 ROUTE 만.\n"
        "형식 — GFM 인용 블록(blockquote): 각 줄 '> ' 로 시작, 첫 줄 볼드 헤더, 4개 필드는\n"
        "'> - ' 불릿 + 볼드 라벨(middle-dot '·' 나 평문 들여쓰기 금지 — 그러면 마크다운이\n"
        "리스트로 인식 못 해 라벨이 뭉친다). 아래를 그대로 따르되 <…> 만 채움:\n"
        "> **ANALYZE**\n"
        "> - **목적**: <이 요청으로 달성하려는 것 한 줄>\n"
        "> - **핵심 요구**: <반드시 만족할 것 — 쉼표로 나열>\n"
        "> - **제약**: <지켜야 할 한계·보존 범위 / 없으면 '특이사항 없음'>\n"
        "> - **모호한 점**: <해석이 갈리는 지점 / 없으면 '없음'>\n"
        "모호한 점이 '없음' 이 아니면 ROUTE·작업으로 넘어가지 말고 그 지점을 먼저\n"
        "사용자에게 확인하라.\n\n"
        "출력 순서 (ROUTE 는 매 턴 낸다): 응답 맨 처음에, 게이트\n"
        "해당 시 ANALYZE 블록을 *먼저* 통째로 내고 그 *바로 아래* 줄에 ROUTE — 즉\n"
        "ANALYZE 가 ROUTE 보다 위. (다른 블록이 'ROUTE 를 맨 앞에' 라고 해도 게이트 해당 시엔 ANALYZE\n"
        "가 맨 앞 자리를 차지하고 ROUTE 는 그 다음 줄 — 이 순서가 우선한다.) 게이트 비해당\n"
        "이면 ANALYZE 없이 ROUTE 만 맨 앞 줄에. 레인 변화와 무관하게 매 턴 ROUTE 를\n"
        "낸다(ANALYZE 는 게이트 해당 시에만 추가 — 요구사항 분해는\n"
        "출력 노이즈가 아니라 작업 정확도용).\n"
        "ROUTE 도 ANALYZE 와 같은 GFM 인용 블록(평문·middle-dot 금지). 둘을 같이 낼 때는\n"
        "ANALYZE 블록 끝에 빈 인용 줄('>') 하나로 띄우고 그 아래 ROUTE 줄을 붙여 하나의\n"
        "인용 박스로 묶는다(본문과 한눈에 분리). 형식:\n\n"
        "(게이트 해당 시 — ANALYZE+ROUTE 한 인용 박스; ANALYZE 4개 필드는 위 템플릿대로)\n"
        "> **ANALYZE**\n"
        "> ...(위 4개 필드)\n"
        ">\n"
        f"> **ROUTE →** <{verdict_enum}|handle-directly> · <한 줄 근거>\n\n"
        "(게이트 비해당 시 — ROUTE 만)\n"
        f"> **ROUTE →** <{verdict_enum}|handle-directly> · <한 줄 근거>\n\n"
        "닫는 재확인(턴 종료 전): ROUTE 를 맨 앞에 찍는 건 *행동 전 commitment 게이트*라\n"
        "위치를 끝으로 옮기지 않는다 — 대신 본문을 다 쓴 *뒤* 대조하라: 실제로 한 작업이\n"
        "이번 판정 레인과 같았나? 깊이 생각해보니(또는 본문 도중 무거운 하위작업·산출물\n"
        "수정으로) 레인이 달라졌다면 그 사실을 한 줄로 명시하고 *갱신된 ROUTE 를 다시\n"
        "찍어라*. 레인이 안 바뀌었으면 이미 맨 앞에 ROUTE 를 냈으니 추가 출력은 불필요\n"
        "(중복 금지) — 판정만 조용히 확인하고 넘어간다.\n"
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
