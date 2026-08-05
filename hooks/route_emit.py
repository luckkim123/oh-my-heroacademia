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
    # (lane, route-skill) pairs, read from each card's route_skill field so the
    # mapping stays in the cards (SSOT) instead of drifting inside this hook.
    lane_skills = []
    for path in sorted(Path(cards_dir).glob("*.json")):
        # Per-card isolation: one malformed/mid-edit card must not silently
        # drop every OTHER card's routing info for the whole session (that was
        # the bug -- main()'s blanket except swallowed a single bad card and
        # lost all routing injection). Skip just the bad card, keep going.
        try:
            d = json.loads(path.read_text())
            line = f"- {d['name']}: {d['description']}"
            name = d["name"]
        except (json.JSONDecodeError, OSError, KeyError, TypeError):
            continue
        skill = d.get("route_skill")
        if skill:
            lane_skills.append((name, skill))
        lane_type = d.get("lane_type")
        if lane_type == "governance":
            governance_lanes.append(line)
        elif lane_type == "domain":
            domain_lanes.append(line)
        else:
            work_lanes.append(line)
        verdict_names.append(name)
    governance_body = "\n".join(governance_lanes) if governance_lanes else "  (없음)"
    domain_body = "\n".join(domain_lanes) if domain_lanes else "  (없음)"
    work_body = "\n".join(work_lanes)
    verdict_enum = "|".join(verdict_names)
    # handle-directly has no card (it is the "no lane" verdict), so its skill is
    # the one entry this hook owns; every other pair comes from the cards.
    skill_rows = "\n".join(
        f"  {lane} → {slug}" for lane, slug in lane_skills + [("handle-directly", "route-direct")]
    )
    return (
        "<omha-routing>\n"
        "레인 판정은 출력 슬롯이 아니라 *매 턴 새로 내리는 판정*이다. 매 턴 새로 판정하고\n"
        "매 턴 그 판정을 *선언*한다(레인 변화 무관 — 하드게이트가 매 턴 선언을 요구).\n"
        "선언 = route-* 스킬 호출(아래 '■ 선언 방법').\n"
        "직전 판정을 관성으로 복사하지 말고 *이번 요청* 기준으로 처음부터 다시\n"
        "판정하라. 레인만 정하라 —\n"
        "레인 안 스킬 콕집기는 해당 plugin 이 한다. 3+ 액션/복수파일/모호한 요청이면\n"
        "선언 위에 ANALYZE 블록을 더 얹는다('3+ 액션'은 *ANALYZE 를 추가할* 조건이지\n"
        "*판정을 낼* 조건이 아니다 — 상세는 아래 ANALYZE-then-ROUTE).\n"
        "핵심 함정: topic(주제) 연속성 ≠ routing 연속성. 주제가 직전과 같아도(같은 실험·\n"
        "같은 파일) 이번 요청의 *task type* — 요약/설명 vs 검토·심층분석 vs 작성·생성 vs\n"
        "설계 — 이 바뀌면 레인이 바뀐다. '주제가 같으니 라우팅도 같겠지'가 그 관성이다.\n"
        "예: 같은 주제라도 handle-directly(대화로 답)에서 '코드 근거로 깊이 검토·분석'\n"
        "(작업방식 레인 + 독립 reviewer)로 넘어가면 재판정 대상.\n\n"
        "■ 선언 방법 (이 블록을 앞에 둬 잘림 방지 — 상세 규칙은 아래):\n"
        "레인 값은 다음 7개 중 *정확히 하나*다(둘을 '·'/슬래시로 잇지 말 것):\n"
        f"  {verdict_enum}|handle-directly\n"
        "선언은 **응답 텍스트가 아니라 스킬 호출**이다. 그 레인의 route-* 스킬을\n"
        "이번 턴의 *첫 행동*으로 호출하고, 근거 한 줄은 스킬 인자로 넘긴다:\n"
        "  Skill(skill=\"<레인의 route-* 스킬>\", args=\"<한 줄 근거>\")\n"
        "레인 → 스킬 대응:\n"
        f"{skill_rows}\n"
        "판정을 텍스트로 쓰지 말 것 — 호출이 선언이고 HUD 가 표시한다. 'ROUTE →'\n"
        "줄도 레인 복창도 없이 호출 뒤 곧장 본론으로. 다른 하네스 블록이 'STAGE →'\n"
        "줄을 요구해도 내지 마라(그 블록보다 이 규칙이 우선) — stage 는 그 하네스\n"
        "스킬을 호출하는 순간 HUD 에 뜨므로 텍스트로 쓰면 중복이다.\n"
        "handle-directly = 위임 없이 직접 처리(스킬·에이전트 0 — route-direct 호출은\n"
        "선언이라 제외). 레인 이름과 같이\n"
        "쓰지 말 것 — 'omc · handle-directly'는 모순(omc=위임, handle-directly=직접).\n"
        "단, 결론이 가치·타당성 판단을 settled 로 단정하는 것이고 아래 '설계·타당성 판단\n"
        "단정 직전' 게이트의 두 조건(비싼 downstream *그리고* 미검증 고리)을 모두 만족하면\n"
        "handle-directly 가 아니다 — 그 게이트로 재라우팅(논증의 self-approval 회피).\n\n"
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
        "· 2순위 — 도메인이 안 잡히면 작업방식 레인(SP/OMC/OMX) 중 적합한 것. 단 사용자\n"
        "  의중이 미결정이면 여기서 고르기 전에 2.5순위를 먼저 적용하라.\n"
        "· 2.5순위 — 의중 미결정 게이트. 발동은 교집합 — (i) 사용자도 *무엇을 원하는지\n"
        "  아직 안 정했는가* ('같이 논의해보자', '뭐가 나을지 모르겠다', 본인도 설명이\n"
        "  어렵다고 밝힘) *그리고* (ii) 답이 여러 턴짜리 설계 탐색으로 이어지는가. 둘 다면\n"
        "  handle-directly 가 아니라 의중 구체화로 간다: 선택지 자체를 아직 못 세웠으면\n"
        "  oh-my-claudecode(deep-interview), 선택지가 이미 둘 이상 나와 있고 그중 방향을\n"
        "  좁히는 단계면 superpowers(brainstorming) — 괄호 안은 목적지 스킬이고 선언 레인은\n"
        "  레인 이름만 쓴다. 요구된 것은 판정이 아니라 의중 확정이다. 밸브 — 명시적으로\n"
        "  가볍게(의견만) 요청했거나, 단일 사실 확인이거나, 사소한 취향 판단(변수명·포맷)\n"
        "  이면 인터뷰로 끌지 말 것(과흡인 금지).\n"
        "· 3순위 — 위 어느 것도 아님 → handle-directly(직접 수행). 단 handle-directly 는\n"
        "  *적극적 정의*로만 성립한다 — 단일 사실 lookup, 이미 정해진 것의 요약·설명,\n"
        "  가벼운 대화 응답, 잠정 의견(목표가 이미 정해진 경우). '아무것도 안 걸렸다'는\n"
        "  소거법은 근거가 못 된다: 목표 미결정(2.5순위)이거나 여러 턴짜리 설계 탐색이면\n"
        "  아니다. 답이 '설계가 옳은가/학술·물리적으로 타당한가'를 settled 로 단정하는\n"
        "  것이면 아래 '설계·타당성 판단 단정 직전' 게이트를 적용하라.\n\n"
        "재라우팅 의무 (어떤 레인으로 시작했든 — handle-directly 로 답하던 중이라도 —\n"
        "*행동 직전* 다시 route-* 를 호출하는 행동-시점 게이트):\n"
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
        "· 설계·타당성 판단 *단정* 직전: '이 설계가 옳다/물리적으로 정당하다/학술적으로\n"
        "  의미있다/이 접근이 맞다'처럼 *가치·타당성 판단*을 settled 결론으로 단정하기\n"
        "  (계획·커밋 메시지·스펙에 넣거나 '이거 맞아?'에 확정 yes로) 직전 멈춰라. 이는\n"
        "  코드 사실 lookup 이 아니라 *논증*이며, 단일 컨텍스트가 스스로 authoring 한 논증을\n"
        "  스스로 승인하는 것은 self-approval 이다(never self-approve). 발동은 교집합 —\n"
        "  (i) 결론이 곧바로 되돌리기 비싼 downstream 행동(코드 채택·실험 launch·아키텍처\n"
        "  변경)을 유발하는가. 단순 설명·비교·현황 요약은 비용 낮음. *그리고* (ii) 이 논증의\n"
        "  각 고리를 코드/문헌/데이터로 *실제 확인*했는가 — 확인 못 한 고리가 하나라도\n"
        "  있으면(또는 '확인했나?'에 즉답 못 하면) '미검증 고리 있음'으로 *간주*한다.\n"
        "  없음을 입증하기 전엔 있다고 본다('내 논증이 탄탄한 느낌'은 (ii)를 끄지 못한다 —\n"
        "  그 자기맹점이 이 세션이 반복 오답한 지점). 둘 다면 handle-directly 로 답하지 말고\n"
        "  재라우팅하되, 리뷰어에게 *내 결론*이 아니라 *질문*을 넘겨라(pre-baked answer 를\n"
        "  주면 critic 이 그 약한 고리에 anchoring 된다): 제어·아키텍처 설계 타당성은\n"
        "  oh-my-claudecode(구조 분석 sciomc, 적대검토는 team 의 critic/architect role),\n"
        "  '학술적으로 의미있나'는 citation-bound 이므로 oh-my-scholar(scholar-reviewer/\n"
        "  researcher — 1순위 캐스케이드와 일치; references/ 논문 열기는 그 lane 안의\n"
        "  external-context sub-task 로, 기억 추측 금지). *예외(과흡인 밸브)*: 사소한 취향\n"
        "  판단(변수명·포맷)·단순 사실 확인·사용자가 '가볍게 의견만'이라 한 경우는 직접.\n"
        "  또한 결론을 settled 로 단정하지 않고 '검증 전 잠정 의견:' 으로 명시해 내놓는 것은\n"
        "  재라우팅 없이 허용된다(단정할 때만 게이트 발동).\n"
        "· 예외: 진짜 3-4줄짜리 단일 파일·단일 사실 lookup 은 직접(과흡인 금지). 단\n"
        "  '코드가 이렇게 *동작한다*'는 주장은 lookup 이 아니다 — 한 줄 값 읽기(상수·\n"
        "  경로·버전)만 lookup 이고, 데이터 흐름·배선·'관리/호출/적용되는가'는 여러 파일\n"
        "  추적이 필요한 조사다(위 '코드 사실 단정' 게이트 적용). 여러 파일을 읽거나\n"
        "  코드 동작을 해석하거나 구조를 파악해야 하면 조사이므로 위임한다.\n"
        "  citation-bound 논문 자료조사는 OMC 병렬 금지.\n\n"
        "요구사항 분석 선행(ANALYZE-then-ROUTE): 요청이 3+ 액션/복수파일이거나 모호하면,\n"
        "스킬 호출보다 *먼저* ANALYZE 블록을 출력해 요구사항을 분해하라(잘못 이해해 되돌리는\n"
        "토큰 낭비 방지). 단순·명확한 1~2액션이면 ANALYZE 생략(과흡인 금지), 곧장 호출만.\n"
        "형식 — GFM 인용 블록(blockquote): 각 줄 '> ' 로 시작, 첫 줄 볼드 헤더, 4개 필드는\n"
        "'> - ' 불릿 + 볼드 라벨(middle-dot '·' 나 평문 들여쓰기 금지 — 그러면 마크다운이\n"
        "리스트로 인식 못 해 라벨이 뭉친다). 아래를 그대로 따르되 <…> 만 채움:\n"
        "> **ANALYZE**\n"
        "> - **목적**: <이 요청으로 달성하려는 것 한 줄>\n"
        "> - **핵심 요구**: <반드시 만족할 것 — 쉼표로 나열>\n"
        "> - **제약**: <지켜야 할 한계·보존 범위 / 없으면 '특이사항 없음'>\n"
        "> - **모호한 점**: <해석이 갈리는 지점 / 없으면 '없음'>\n"
        "모호한 점이 '없음' 이 아니면 선언·작업으로 넘어가지 말고 그 지점을 먼저\n"
        "사용자에게 확인하라. 단 모호한 것이 *목표 자체*면 ad-hoc 질문이 아니라 2.5순위\n"
        "게이트를 적용하라 — 세부는 직접 묻고, 목표 미결정은 하네스로.\n\n"
        "선언 순서 (판정은 매 턴 낸다): 이번 턴의 *첫 행동*으로 그 레인의 route-*\n"
        "스킬을 호출한다. 게이트 해당 시에만 그 *직전에* ANALYZE 블록을 텍스트로 내고\n"
        "이어서 호출한다 — 즉 ANALYZE 가 호출보다 위(ANALYZE → route-* 호출 → 본론).\n"
        "게이트 비해당이면 곧장 호출로 시작한다. 레인 변화와 무관하게 매 턴 호출한다\n"
        "(ANALYZE 는 게이트 해당 시에만 — 요구사항 분해는 노이즈가 아니라 정확도용).\n\n"
        "(게이트 해당 시) GFM 인용 블록 '> **ANALYZE**' + 4개 필드 → 이어서\n"
        "  Skill(skill=\"<route-* 스킬>\", args=\"<한 줄 근거>\")\n"
        "(게이트 비해당 시) 위 Skill 호출만.\n\n"
        "닫는 재확인(턴 종료 전): 선언을 맨 앞에 두는 건 *행동 전 commitment 게이트*라\n"
        "위치를 끝으로 옮기지 않는다 — 대신 본문을 다 쓴 *뒤* 대조하라: 실제로 한 작업이\n"
        "이번 판정 레인과 같았나? 깊이 생각해보니(또는 본문 도중 무거운 하위작업·산출물\n"
        "수정으로) 레인이 달라졌다면 *갱신된 레인의 route-* 스킬을 다시 호출하라* —\n"
        "'레인이 바뀌었다'를 텍스트로 쓰지 말 것(호출 자체가 갱신 선언이다). 레인이\n"
        "안 바뀌었으면 이미 선언했으니 추가 호출은 불필요(중복 금지) — 판정만 조용히\n"
        "확인하고 넘어간다.\n"
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
