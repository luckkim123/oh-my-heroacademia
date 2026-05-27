import json
from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_plugin_json_registers_userpromptsubmit_python_hook():
    m = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert m["name"] == "oh-my-heroacademia"
    assert "version" not in m          # commit-SHA 버저닝 일관
    hooks = m["hooks"]["UserPromptSubmit"]
    cmd = hooks[0]["hooks"][0]
    assert cmd["command"] == "python3"
    assert "${CLAUDE_PLUGIN_ROOT}/hooks/route_emit.py" in cmd["args"]


def test_marketplace_and_plugin_coexist():
    cp = ROOT / ".claude-plugin"
    assert (cp / "marketplace.json").exists()  # 기존 마켓플레이스 유지
    assert (cp / "plugin.json").exists()        # 신규 플러그인
