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
