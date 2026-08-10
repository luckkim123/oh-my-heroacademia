import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))
import json

import route_emit

SKILL_MD = Path(__file__).parent.parent / "skills" / "routing" / "SKILL.md"


def _skill() -> str:
    """The routing skill body.

    The per-prompt hook block is a summary + pointer; the rules it points at
    live here. A rule that moved out of the hook is still *required to exist* —
    it just has to be in this file, and the hook has to name a trigger that
    sends the session to read it."""
    return SKILL_MD.read_text()


def test_skill_body_exists_and_is_discoverable():
    """훅이 가리키는 대상이 실재해야 한다. 포인터만 남기고 본문이 없으면
    규칙이 사라진 것과 같다 — 이 테스트가 그 공백을 잡는다."""
    assert SKILL_MD.is_file(), f"routing skill body missing at {SKILL_MD}"
    body = _skill()
    assert body.startswith("---"), "SKILL.md needs frontmatter to be discoverable"
    assert "name: routing" in body
    # description 은 스킬 목록에 실리는 유일한 부분 — 언제 읽어야 하는지가 거기 있어야
    front = body.split("---")[1]
    assert "description:" in front and len(front) > 200, "description too thin to route on"


def test_hook_points_at_the_skill_with_read_triggers(tmp_path):
    """요약+포인터 구조의 핵심: 포인터가 *언제 읽어야 하는지*를 같이 실어야 한다.
    'ㅇㅇ 스킬이 있다'만 있으면 관성 아래에서 그냥 안 읽힌다."""
    (tmp_path / "omc.json").write_text(json.dumps(
        {"name": "oh-my-claudecode", "description": "Throughput lane.", "lane_type": "work"}))
    ctx = route_emit.build_routing_context(tmp_path)
    assert route_emit.SKILL_REF in ctx, "hook must name the skill it defers to"
    # 최소 트리거 4종 — 위임 직전 / 산출물 수정 직전 / 단정 직전 / 의중 미결정
    for trigger in ("위임 직전", "수정 직전", "단정하기 직전", "의중 미결정"):
        assert trigger in ctx, f"read-trigger missing from pointer: {trigger}"


def test_context_lists_each_card_lane(tmp_path):
    (tmp_path / "superpowers.json").write_text(json.dumps(
        {"name": "superpowers", "description": "Discipline lane. CORRECTNESS governs."}))
    (tmp_path / "omc.json").write_text(json.dumps(
        {"name": "oh-my-claudecode", "description": "Throughput & autonomy lane."}))
    ctx = route_emit.build_routing_context(tmp_path)
    assert "superpowers" in ctx and "oh-my-claudecode" in ctx
    assert "Discipline lane" in ctx and "Throughput" in ctx
    assert "handle-directly" in ctx          # 3순위 직접 수행 명시
    assert "레인" in ctx or "lane" in ctx     # 레인 판정 강제 문구


def test_context_states_three_tier_cascade(tmp_path):
    """캐스케이드 3계층(1순위 SP/OMC → 2순위 설치 도메인 스킬 → 3순위 직접)이 다 명시돼야.
    이전엔 1순위/3순위 2분기뿐이라 2순위 도메인 계층이 누락됐었다."""
    (tmp_path / "omc.json").write_text(json.dumps(
        {"name": "oh-my-claudecode", "description": "Throughput lane."}))
    ctx = route_emit.build_routing_context(tmp_path)
    # 훅에는 한 줄 요약형으로 4계층이 다 있어야 (거버넌스 → 도메인 → 작업방식 → 직접)
    assert "캐스케이드" in ctx and "도메인" in ctx
    assert "거버넌스" in ctx and "작업방식" in ctx and "handle-directly" in ctx
    # 계층별 세부 판정 기준은 스킬 본문에 (0~3순위 + 2.5순위)
    body = _skill()
    assert "1순위" in body and "2순위" in body and "3순위" in body


def test_context_states_reroute_obligation(tmp_path):
    """도메인 스킬 안에서 작업 중이라도 무거운 cross-lane 하위작업을 만나면
    레인 판정을 다시 하라는 재라우팅 의무가 있어야 (사용자 증상: OMD 안에서 OMC 안 부름)."""
    (tmp_path / "omc.json").write_text(json.dumps(
        {"name": "oh-my-claudecode", "description": "Throughput lane."}))
    ctx = route_emit.build_routing_context(tmp_path)
    assert "도메인" in ctx                       # 도메인 안에서도 적용됨을 명시
    # 훅은 재판정이 필요한 *시점*을 트리거로 싣고, 의무 본문은 스킬에 있다
    assert "위임 직전" in ctx and "수정 직전" in ctx
    body = _skill()
    assert "재라우팅 의무" in body
    assert "다시" in body or "재판정" in body


def test_context_no_a2a_dependency():
    # route_emit 는 stdlib 만 import — a2a 미설치 환경에서도 import 성공
    src = (Path(__file__).parent.parent / "hooks" / "route_emit.py").read_text()
    assert "import a2a" not in src and "from a2a" not in src


def test_context_emits_analyze_before_route(tmp_path):
    """ROUTE 앞에 요구사항 분석(ANALYZE)을 먼저 출력하라는 지시가 있어야 한다.
    사용자 의도: routing 전에 요구사항을 분석·검토해 한 번에 완료(되돌이 토큰 절약)."""
    (tmp_path / "omc.json").write_text(json.dumps(
        {"name": "oh-my-claudecode", "description": "Throughput lane."}))
    ctx = route_emit.build_routing_context(tmp_path)
    assert "ANALYZE" in ctx                          # 훅이 존재와 발동조건은 안다
    # 게이트: 3+ 액션/모호할 때만 (간단 요청엔 안 띄움)
    assert "3+" in ctx or "모호" in ctx
    assert "모호" in ctx
    # 템플릿과 순서 강제는 스킬 본문에 — 거기서도 ANALYZE 가 ROUTE 보다 먼저여야
    body = _skill()
    assert "ANALYZE" in body and "모호한 점" in body
    assert body.index("ANALYZE") < body.index("ROUTE 도 ANALYZE")


def _six_cards(tmp_path):
    """Write all six real-ish cards so the assembled block is full-size, letting us
    assert WHERE the format spec lands relative to the (large) card bodies."""
    cards = {
        "omp": ("oh-my-project", "governance", "A" * 600),
        "omd": ("oh-my-docs", "domain", "B" * 400),
        "oms": ("oh-my-scholar", "domain", "C" * 400),
        "omc": ("oh-my-claudecode", "work", "D" * 600),
        "omx": ("oh-my-experiments", "work", "E" * 400),
        "superpowers": ("superpowers", "work", "F" * 400),
    }
    for fn, (name, lane, desc) in cards.items():
        (tmp_path / f"{fn}.json").write_text(json.dumps(
            {"name": name, "description": desc, "lane_type": lane}))


def test_route_format_spec_lands_in_head_before_card_bodies(tmp_path):
    """The load-bearing format spec — the 7 verdict values + the GFM ROUTE quote
    form + the inertia/re-route rule — must appear BEFORE the long card bodies, so
    it survives preview truncation (the bug: spec was buried after ~7KB of cards)."""
    _six_cards(tmp_path)
    ctx = route_emit.build_routing_context(tmp_path)
    # The card bodies (now digests of the 600 'A'/'D' runs) mark where the bulk
    # begins — match a short prefix so this does not pin LANE_DIGEST_CAP.
    first_card_body = min(ctx.index("A" * 50), ctx.index("D" * 50))
    # The ROUTE GFM format example and the inertia rule must precede the card bulk.
    assert ctx.index("ROUTE →") < first_card_body, "ROUTE format buried after card bodies"
    assert "관성" in ctx and ctx.index("관성") < first_card_body, "inertia rule buried after cards"


def test_context_forces_analyze_above_route_explicitly(tmp_path):
    """순서 강제 문구가 명시적으로 있어야 한다. 'ROUTE 를 맨 앞에' 라는
    다른 블록 문구와 충돌해 모델이 ROUTE 를 먼저 내는 회귀가 있었다 —
    'ANALYZE 가 ROUTE 보다 위' 를 못박는 문구로 모순을 제거한다."""
    (tmp_path / "omc.json").write_text(json.dumps(
        {"name": "oh-my-claudecode", "description": "Throughput lane."}))
    ctx = route_emit.build_routing_context(tmp_path)
    body = _skill()
    # 순서를 명시적으로 못박는 강제 문구 (스킬 본문이 출력 형식의 SSOT)
    assert "ANALYZE 가 ROUTE 보다 위" in body or "ANALYZE 를 ROUTE 보다 먼저" in body
    # 모호한 '맨 앞 ROUTE' 단독 지시가 없어야 (있으면 ANALYZE 와 충돌) — 양쪽 다
    assert "맨 앞에 이 한 줄로" not in ctx and "맨 앞에 이 한 줄로" not in body


def test_no_omit_clause_in_prose(tmp_path):
    """BUG-2 (옵션 b): '레인이 같으면 ROUTE 줄을 생략' 하는 조건부-출력 지시가 없어야 한다.
    정책은 '매 턴 ROUTE 출력'으로 하드게이트(route_guard/route_stop_guard)와 일치한다 —
    생략 조항이 남아 있으면 '매 턴 ROUTE'를 요구하는 게이트와 지시가 모순된다.
    ROUTE 판정 자체는 여전히 매 턴 새로 내려야 한다(관성 복사 금지)는 취지는 보존."""
    (tmp_path / "omc.json").write_text(json.dumps(
        {"name": "oh-my-claudecode", "description": "Throughput lane.", "lane_type": "work"}))
    ctx = route_emit.build_routing_context(tmp_path)
    # 생략 지시 문구가 사라져야 한다 (정확한 부분문자열)
    assert "ROUTE 줄 자체를\n생략한다" not in ctx
    assert "ROUTE 줄만 생략" not in ctx
    assert "레인이 바뀌었을 때만" not in ctx
    # 매 턴 ROUTE 출력 정책이 명시돼야 한다
    assert "매 턴" in ctx and "ROUTE" in ctx
    # 관성 방지(이번 요청 기준 재판정) 취지는 보존돼야 한다
    assert "관성" in ctx


# ─── group: per-card isolation — one malformed card must not sink all of them ─

def test_build_routing_context_skips_malformed_card_keeps_others(tmp_path):
    """One card missing a required field must not raise out of the loop and lose
    every OTHER valid card's routing info -- only that card is skipped."""
    (tmp_path / "omc.json").write_text(json.dumps(
        {"name": "oh-my-claudecode", "description": "Throughput lane."}))
    (tmp_path / "broken.json").write_text(json.dumps({"description": "no name field"}))
    ctx = route_emit.build_routing_context(tmp_path)
    assert "oh-my-claudecode" in ctx and "Throughput lane" in ctx


def test_build_routing_context_skips_non_dict_card_keeps_others(tmp_path):
    """Regression: a card file that is valid JSON but not a dict (e.g. a top-level
    list -- a plausible mid-edit state) makes `d['name']` raise TypeError, which
    the old except tuple (JSONDecodeError, OSError, KeyError) did not catch. That
    let TypeError propagate out of the loop, and main()'s blanket `except
    Exception: return 0` then swallowed EVERY card's routing injection -- the
    exact failure this per-card isolation is supposed to prevent."""
    (tmp_path / "omc.json").write_text(json.dumps(
        {"name": "oh-my-claudecode", "description": "Throughput lane."}))
    (tmp_path / "broken.json").write_text(json.dumps(["not", "a", "dict"]))
    ctx = route_emit.build_routing_context(tmp_path)
    assert "oh-my-claudecode" in ctx and "Throughput lane" in ctx


def test_main_still_emits_when_one_card_is_malformed(tmp_path, monkeypatch, capsys):
    """e2e: main() must still print the routing envelope with the valid card's
    info even when a sibling card file is malformed, instead of the previous
    blanket `except Exception: return 0` silently swallowing everything."""
    (tmp_path / "omc.json").write_text(json.dumps(
        {"name": "oh-my-claudecode", "description": "Throughput lane."}))
    (tmp_path / "broken.json").write_text(json.dumps({"description": "no name field"}))
    monkeypatch.setattr(route_emit, "CARDS_DIR", tmp_path)
    rc = route_emit.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert out.strip(), "malformed sibling card must not swallow all routing output"
    ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert "oh-my-claudecode" in ctx


def test_context_has_design_validity_gate(tmp_path):
    """판단형 검토(설계·타당성)가 self-approval 로 handle-directly 에 새는 결함을 막는
    재라우팅 게이트가 있어야 한다 (yaw-rate 사례: 단일 컨텍스트가 논증을 authoring 하고
    같은 컨텍스트에서 승인). 코드-사실 게이트(d)는 '이 코드가 X한다' 단정만 커버해
    가치·타당성 *논증*을 놓쳤다."""
    (tmp_path / "omc.json").write_text(json.dumps(
        {"name": "oh-my-claudecode", "description": "Throughput lane.", "lane_type": "work"}))
    ctx = route_emit.build_routing_context(tmp_path)
    body = _skill()
    # (0) 훅은 이 게이트로 가는 트리거를 실어야 한다 — 안 실으면 스킬을 읽을 계기가 없다
    assert "설계·타당성" in ctx and "단정하기 직전" in ctx
    # (1) 게이트 present
    assert "설계·타당성 판단" in body
    # (2) 미검증-기본값 뒤집기 문구 present — CRITICAL 회귀 가드. 이게 없으면 미래 편집이
    #     조용히 self-assess 방식("내 논증에 약한 고리 있나?")으로 되돌려도 테스트가 못 잡는다.
    #     세션이 자기맹점 때문에 (ii)를 끌 수 없도록 '입증 전엔 있다고 간주' 기본값이 박혀야.
    assert "없음을 입증하기 전엔 있다고 본다" in body
    # (3) 학술 타당성 목적지가 oh-my-scholar (1순위 캐스케이드 일치 — OMC 로 보내면 모순)
    assert "학술적으로 의미있나" in body and "oh-my-scholar" in body
    # (4) 과흡인 밸브 — '잠정 의견' escape 가 있어야 라우팅 마비 방지
    assert "잠정 의견" in body


# ─── group: intent-crystallization — an undecided GOAL must not fall to handle-directly ─

def test_context_has_intent_crystallization_branch(tmp_path):
    """캐스케이드에 '목표 자체가 미결정' 분기가 있어야 하고, 그 목적지 스킬 이름이
    *주입되는* 텍스트 안에 있어야 한다.

    결함(2026-08-05 재현): 카드의 skills[].examples 와 triggers 는 route_emit 이
    주입하지 않는다(description 만 주입). 그래서 sp 카드의 'no direction yet' 예시도,
    omc 의 deep-interview 도 세션에서 보이지 않았고, 목표 미결정 요청은 소거법으로
    handle-directly 에 떨어져 3턴 연속 요청받지 않은 결론이 생산됐다.
    Fails if the branch (or either destination name) is deleted from
    build_routing_context — 이 assert 는 fix 이전 트리에서 실제로 실패한다."""
    (tmp_path / "omc.json").write_text(json.dumps(
        {"name": "oh-my-claudecode", "description": "Throughput lane.", "lane_type": "work"}))
    ctx = route_emit.build_routing_context(tmp_path)
    body = _skill()
    # (0) 훅에 트리거가 있어야 — '의중 미결정'이면 스킬을 읽으라는 지시
    assert "의중 미결정" in ctx
    # (1) 분기 present — 목표 미결정을 판정 대상으로 삼는다
    assert "의중 미결정 게이트" in body
    # (2) 도달 가능한 목적지 스킬이 *이름으로* 실려야 (F1: examples/triggers 는 안 나감)
    assert "deep-interview" in body and "brainstorming" in body
    # (3) 과흡인 밸브 — 가벼운 요청까지 인터뷰로 끌면 원래 버그보다 나쁜 회귀
    assert "인터뷰로 끌지 말 것" in body


def test_handle_directly_is_positively_defined(tmp_path):
    """handle-directly 가 '아무것도 안 걸렸다'는 *소거법*만으로 성립하면 안 된다.
    Fails if the positive definition is reverted to the exclusion-only 3순위 line."""
    (tmp_path / "omc.json").write_text(json.dumps(
        {"name": "oh-my-claudecode", "description": "Throughput lane.", "lane_type": "work"}))
    ctx = route_emit.build_routing_context(tmp_path)
    # 소거법 금지는 판정 순간에 필요하므로 훅에 남는다 (스킬을 안 읽어도 걸려야 한다)
    assert "적극적 정의" in ctx
    assert "소거법은 근거가 못 된다" in ctx
    # 미결정 목표는 handle-directly 가 아니라는 연결이 명시돼야 (2.5순위와 결합)
    assert "여러 턴짜리 설계 탐색" in _skill()


def test_emitted_context_stays_under_char_ceiling():
    """이 블록은 *모든 세션의 모든 턴*에 주입된다 — 증가는 영구 비용이다.

    ⚠️ 단위는 CHARACTER 다. 바이트가 아니다. 이 가드는 2026-08-10 까지 바이트로
    쟀고, 그래서 실제 사고를 못 잡았다: 블록이 21,950 B(가드 22,300 B 통과)인데
    한국어라 15,714 자였고, Claude Code 는 hook additionalContext 를 ~15K *자*
    에서 잘라 파일로 빼버렸다 — 라우팅 규칙의 86%가 조용히 모델에 안 닿았다.
    훅은 exit 0, 경로도 주입되니 겉보기엔 정상이라 아무 알람도 울리지 않는다.

    실측 경계: 12,537 자(16.3 KB) 통과 / 15,714 자(21.9 KB) 잘림. 정확한 상수는
    확인 못 했다. 이제 훅은 요약+포인터뿐이라 상한을 4,000 자로 조인다 — 상세가
    스킬 본문으로 내려간 이상 훅이 다시 커질 이유가 없고, 여유를 남겨두면 그
    여유만큼 산문이 다시 기어든다. 상한을 올려 무마하지 말 것."""
    ctx = route_emit.build_routing_context(route_emit.CARDS_DIR)
    size = len(ctx)
    assert size <= 4_000, f"per-turn block grew to {size} chars — move it to skills/routing/SKILL.md"


def test_per_turn_block_is_a_summary_not_the_manual(tmp_path):
    """요약+포인터 구조의 회귀 가드: 카드 본문 전문이 훅에 다시 실리면 실패한다."""
    body = "Lane header sentence. " + "Detail sentence that must survive. " * 20
    (tmp_path / "omc.json").write_text(json.dumps(
        {"name": "oh-my-claudecode", "description": body, "lane_type": "work"}))
    turn = route_emit.build_routing_context(tmp_path)
    assert body.strip() not in turn, "per-turn block must carry only the digest"
    assert "…" in turn, "a truncated digest must say so"
    # 잘린 본문을 어디서 읽는지 스킬이 알려줘야 (드리프트 방지: 사본을 두지 않는다)
    assert "cards/" in _skill(), "skill must point at the card SSOT for full lane bodies"


def test_digest_keeps_whole_sentences_and_marks_truncation():
    short = "Document DOMAIN lane."
    assert route_emit._digest(short) == short          # 안 잘리면 '…' 없음
    long = "First sentence here. " + "Filler sentence. " * 40
    d = route_emit._digest(long)
    assert len(d) <= route_emit.LANE_DIGEST_CAP + 2    # '…' 여유
    assert d.startswith("First sentence here.")
    assert d.endswith("…")
