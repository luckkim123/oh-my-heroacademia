import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))
import json
import route_emit


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
    assert "1순위" in ctx and "2순위" in ctx and "3순위" in ctx
    # 2순위 = 설치된 도메인 스킬 (OMD/ppt 등) — 레인이 아닌 도메인 처리기
    assert "도메인" in ctx


def test_context_states_reroute_obligation(tmp_path):
    """도메인 스킬 안에서 작업 중이라도 무거운 cross-lane 하위작업을 만나면
    레인 판정을 다시 하라는 재라우팅 의무가 있어야 (사용자 증상: OMD 안에서 OMC 안 부름)."""
    (tmp_path / "omc.json").write_text(json.dumps(
        {"name": "oh-my-claudecode", "description": "Throughput lane."}))
    ctx = route_emit.build_routing_context(tmp_path)
    assert "다시" in ctx or "재판정" in ctx     # 재라우팅 의무 문구
    assert "도메인" in ctx                       # 도메인 안에서도 적용됨을 명시


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
    assert "ANALYZE" in ctx                          # 분석 블록 존재
    # 출력 순서가 ANALYZE → ROUTE 여야 (분석이 먼저)
    assert ctx.index("ANALYZE") < ctx.index("ROUTE →")
    # 게이트: 3+ 액션/모호할 때만 (간단 요청엔 안 띄움)
    assert "3+" in ctx or "모호" in ctx
    # 모호한 점이 있으면 작업 전 되묻는다는 강제
    assert "모호" in ctx


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
    # The big card bodies (600 'A'/'D' runs) mark where the bulk begins.
    first_card_body = min(ctx.index("A" * 600), ctx.index("D" * 600))
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
    # 순서를 명시적으로 못박는 강제 문구
    assert "ANALYZE 가 ROUTE 보다 위" in ctx or "ANALYZE 를 ROUTE 보다 먼저" in ctx
    # 모호한 '맨 앞 ROUTE' 단독 지시가 없어야 (있으면 ANALYZE 와 충돌)
    assert "맨 앞에 이 한 줄로" not in ctx
