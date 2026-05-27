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


def test_context_no_a2a_dependency():
    # route_emit 는 stdlib 만 import — a2a 미설치 환경에서도 import 성공
    src = (Path(__file__).parent.parent / "hooks" / "route_emit.py").read_text()
    assert "import a2a" not in src and "from a2a" not in src
