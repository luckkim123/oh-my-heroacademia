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
