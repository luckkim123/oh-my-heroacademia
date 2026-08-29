"""omha stage-1 UserPromptSubmit hook: read cards/*.json (stdlib only), inject
the lane-routing *decision surface*. NO a2a-sdk (runtime dep = 0).

The card knowledge lives in cards/*.json (single source of truth). This hook
only *reads and injects* it — it never embeds the knowledge inline, so there is
no drift (the anti-pattern the legacy claude-settings routing had between
using-omc/SKILL.md and routing-verdict-reminder.py).

Summary + pointer, not the manual (2026-08-10). The block had grown to 15,714
chars and Claude Code truncates hook additionalContext above ~15K chars: it
persisted the block to a file and injected a 2 KB preview, so ~86% of the rules
silently stopped reaching the model. The byte-budget guard missed it because the
host limit is counted in CHARACTERS, not bytes (21,950 B of Korean = 15,714
chars: under the 22,300 B guard, over the host's limit).

So this hook now carries only what is needed to *make and emit* the verdict —
the 7 lane values, a digest of each lane, the cascade in one line, the output
format — plus a pointer to the `routing` skill with explicit read-triggers. The
cascade detail, the intent-crystallization gate, the five re-routing gates, the
ANALYZE template and the output-order rules live in skills/routing/SKILL.md,
loaded on demand instead of paid for on every prompt.

Emission is scoped to work turns (0.9.0). The judgment still runs every turn, but
the ROUTE line is only *printed* when the turn calls a tool route_guard gates.
Measured on one vault (25 transcripts, 206 turns), 111 turns (53.9%) called no
such tool: they touch nothing, so a wrong lane there costs nothing, and the line
was pure noise on the reader's screen. The Stop backstop that used to force a
line on those turns is retired with it — see hooks/route_stop_guard.py."""
import json
import re
import sys
from pathlib import Path

CARDS_DIR = Path(__file__).resolve().parent.parent / "cards"

# Per-lane digest cap. The routing decision needs "what work belongs here +
# precedence"; the rest of a card body is read from the card itself when the
# digest does not settle it (the skill says where). 240 is what it takes for the
# fat governance/work cards to still carry their route-here clause.
LANE_DIGEST_CAP = 240

SKILL_REF = "oh-my-heroacademia:routing"

# ─── handle-directly: ONE definition, emitted once ────────────────────────────
# 2026-08-29: this block carried TWO, and they disagreed. A *mechanism*
# definition sat in the ROUTE-format section ("위임 없이 직접 처리(스킬·에이전트 0)")
# and a *task-type* definition sat in the cascade. The mechanism one wins by
# being first and by being trivially satisfiable: any turn that happened not to
# delegate passes it, which is the outcome of the choice, never its ground.
# Measured on this vault's routing log the same day — of 253 work turns carrying
# the `work` flag, 45 declared handle-directly alone, and 20 of those (44%)
# edited files, one of them 14 distinct files over 71 tool calls.
# Keep exactly one node; tests/test_route_emit.py parses for it.
HD_DEF_MARKER = "■ handle-directly 판정 정의"
HD_POSITIVE_CASES = (
    "단일 사실 lookup",
    "이미 정해진 것의 요약·설명",
    "가벼운 대화 응답",
)
HANDLE_DIRECTLY_DEF = (
    f"{HD_DEF_MARKER} — *적극적 정의* 셋 중 하나일 때만 성립한다:\n"
    f"  (a) {HD_POSITIVE_CASES[0]}  (b) {HD_POSITIVE_CASES[1]}"
    f"  (c) {HD_POSITIVE_CASES[2]}·잠정 의견\n"
    "셋 중 어디에도 못 넣으면 handle-directly 가 아니다 — **2순위 작업방식으로 내려라**\n"
    "(도메인이 없으면 oh-my-claudecode). '아무것도 안 걸렸다'는 소거법은 근거가 못 된다.\n"
    "⚠️ '스킬·에이전트를 안 썼다'는 결과지 근거가 아니다 — 위임 여부로 판정하지 마라.\n\n"
)


def _digest(desc: str) -> str:
    """Cut a card body down to LANE_DIGEST_CAP characters.

    Always spends the whole budget. Dropping any sentence that would overflow
    was the obvious version and it is wrong here: several cards open with a
    short label ("Project-structure GOVERNANCE lane.") followed by one ~470-char
    sentence carrying the entire route-here rule, so sentence-granular selection
    emitted the label alone and nothing to route on. Prefer a sentence boundary
    only when one falls in the last 40% of the budget; otherwise cut on a word."""
    desc = desc.strip()
    if len(desc) <= LANE_DIGEST_CAP:
        return desc
    cut = desc[:LANE_DIGEST_CAP]
    ends = list(re.finditer(r"[.!?](?=\s|$)", cut))
    if ends and ends[-1].end() >= LANE_DIGEST_CAP * 0.6:
        return cut[:ends[-1].end()] + " …"
    return cut.rsplit(" ", 1)[0].rstrip(" ,;:") + " …"


def _read_cards(cards_dir: Path):
    """Yield (name, lane_type, description) per readable card.

    Per-card isolation: one malformed/mid-edit card must not silently drop
    every OTHER card's routing info for the whole session (that was the bug --
    main()'s blanket except swallowed a single bad card and lost all routing
    injection). Skip just the bad card, keep going."""
    for path in sorted(Path(cards_dir).glob("*.json")):
        try:
            d = json.loads(path.read_text())
            yield d["name"], d.get("lane_type"), d["description"]
        except (json.JSONDecodeError, OSError, KeyError, TypeError):
            continue


def lane_values(cards_dir: Path) -> set:
    """Every legal ROUTE value — one per card, plus handle-directly.

    route_guard imports this to reject a declaration outside the enum. Measured
    on this vault 2026-08-29: 15 of 788 logged records named a value outside it,
    and nothing anywhere resisted. Twelve were `research`/`code`/`explore`/
    `execute`/`debug` — OMC agent and skill names, all from teammate/subagent
    turns, which is exactly where the card's vocabulary does not reach. Three
    were `oh-my-orchestrator`, an installed plugin that is deliberately NOT a
    lane (omha cannot assume it is installed — see omha_paths.py).

    Derived from the cards rather than hardcoded: a new card must not need an
    edit here to become routable."""
    return {name for name, _, _ in _read_cards(cards_dir)} | {"handle-directly"}


def build_routing_context(cards_dir: Path) -> str:
    """The per-prompt decision surface.

    Cards split into three kinds by their lane_type field:
      · governance (omp — WHERE files belong / does the tree obey its rules)
      · domain     (oms/omd — WHAT product: paper .tex/.bib, document .pptx…)
      · work-style (omc/sp/omx — HOW you work: throughput, discipline, experiments)

    The cascade is GOVERNANCE-FIRST, then DOMAIN, then work-style (2026-06-05
    design). Governance is an axis ORTHOGONAL to the content domains: the same
    .pptx is omd when you author its content but omp when you ask whether it sits
    in the right folder. The one-line form is here; the reasoning, the tier-2.5
    intent gate and the re-routing obligations are in the routing skill."""
    governance_lanes, domain_lanes, work_lanes = [], [], []
    verdict_names = []
    for name, lane_type, desc in _read_cards(cards_dir):
        line = f"- {name}: {_digest(desc)}"
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
    return (
        "<omha-routing>\n"
        "매 턴 새로 판정하라. 직전 ROUTE 를 관성으로 복사하지 말고 *이번 요청* 기준으로\n"
        "처음부터 다시 판정하라. 핵심 함정: topic(주제) 연속성 ≠ routing 연속성 — 주제가\n"
        "같아도(같은 실험·같은 파일) 이번 요청의 *task type*(요약/설명 vs 검토·심층분석 vs\n"
        "작성·생성 vs 설계)이 바뀌면 레인이 바뀐다. 레인만 정하라 — 레인 안 스킬 콕집기는\n"
        "해당 plugin 이 한다.\n\n"
        "■ 언제 출력하나 — *실작업 턴에만*. 이 턴에 Bash·Edit·Write·Agent·Task 중 하나라도\n"
        "쓴다면 그 첫 도구 호출 *전에* ROUTE 를 찍어라. 순수 대화·설명·요약 턴이면 판정만\n"
        "하고 줄은 찍지 마라 — 사람이 읽는 화면의 소음이고, 아무것도 안 건드리는 턴이라\n"
        "레인이 틀려도 잃을 게 없다. 대화로 시작해 작업으로 넘어가면 도구를 집는 그 시점에\n"
        "찍으면 된다(PreToolUse 게이트가 정확히 거기서 요구한다).\n\n"
        "■ ROUTE 형식 — 값은 다음 7개 중 *정확히 하나*다(둘을 '·'/슬래시로 잇지 말 것):\n"
        f"  {verdict_enum}|handle-directly\n"
        "응답 맨 앞에 GFM 인용 한 줄(평문·middle-dot 금지):\n"
        f"> **ROUTE →** <{verdict_enum}|handle-directly> · <한 줄 근거>\n"
        "표기 규칙(정의 아님): 레인 이름과 같이 쓰지 말 것 — 'omc · handle-directly'는\n"
        "모순이다. 무엇이 handle-directly 인지는 아래 판정 정의 블록 하나가 정한다.\n\n"
        "■ 레인 (요약 — 카드 description 의 앞부분. '…' = 잘림):\n"
        "· 거버넌스 (WHERE — 파일이 어디 속하나·트리가 규칙 지키나. 산출물 축과 직교)\n"
        f"{governance_body}\n"
        "· 도메인 (WHAT — 만드는 산출물이 정함. 명확하면 *먼저* 여기로)\n"
        f"{domain_body}\n"
        "· 작업방식 (HOW — 일하는 방식이 정함)\n"
        f"{work_body}\n\n"
        "■ 캐스케이드 (위에서부터): 0 구조·배치·규칙 문제면 거버넌스 → 1 산출물 도메인이\n"
        "명확하면 그 도메인(논문은 *반드시* oh-my-scholar — citation 가드가 거기에만 있다)\n"
        "→ 2 아니면 작업방식 → 3 아래 판정 정의에 해당하면 handle-directly.\n\n"
        f"{HANDLE_DIRECTLY_DEF}"
        f"■ 상세 규칙은 `{SKILL_REF}` 스킬 본문에 있다 — 캐스케이드 세부(2.5순위 의중\n"
        "미결정 게이트), 재라우팅 의무 5종, ANALYZE 템플릿, 출력 순서, 레인 본문 위치.\n"
        "다음 중 하나라도 해당하면 판정·행동 전에 그 스킬을 *읽어라*:\n"
        "  · 위 요약만으로 레인이 안 갈린다\n"
        "  · 3+ 액션·복수파일·모호한 요청 (ANALYZE 블록이 ROUTE 보다 먼저 나가야 한다)\n"
        "  · Agent/Task/Workflow 위임 직전, 또는 하네스 산출물(exp report.md·omd .pptx·\n"
        "    oms .tex/.bib) 수정 직전 — 스킬을 경유해야 양식·검증 게이트가 발동한다\n"
        "  · 코드 사실('이 코드가 X 한다')이나 설계·타당성을 settled 로 단정하기 직전\n"
        "  · 사용자가 무엇을 원하는지 아직 안 정한 상태(의중 미결정)\n"
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
