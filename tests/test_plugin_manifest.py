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


def test_plugin_json_registers_pretooluse_cross_lane_hook():
    """The push channel for cross-lane routing — fires on Write/Edit/Skill
    only. Read/Bash are excluded (Read floods, Bash needs command parsing)."""
    m = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    pretool = m["hooks"]["PreToolUse"]
    assert pretool, "PreToolUse hook missing"
    cmd = pretool[0]["hooks"][0]
    assert pretool[0]["matcher"] == "Write|Edit|Skill"
    assert cmd["command"] == "python3"
    assert "${CLAUDE_PLUGIN_ROOT}/hooks/cross_lane_emit.py" in cmd["args"]


def test_plugin_json_registers_pretooluse_route_guard():
    m = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    pretool = m["hooks"]["PreToolUse"]
    entries = [e for e in pretool if any(
        "${CLAUDE_PLUGIN_ROOT}/hooks/route_guard.py" in h.get("args", [])
        for h in e["hooks"])]
    assert entries, "route_guard PreToolUse entry missing"
    e = entries[0]
    # Real-work tools are gated; read-only tools must NOT be in the matcher.
    for tool in ("Bash", "Agent", "Task", "Edit", "Write"):
        assert tool in e["matcher"], f"{tool} not gated"
    assert "Read" not in e["matcher"] and "Grep" not in e["matcher"]


def test_plugin_json_registers_stop_route_guard():
    m = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    stop = m["hooks"]["Stop"]
    cmd = stop[0]["hooks"][0]
    assert "${CLAUDE_PLUGIN_ROOT}/hooks/route_stop_guard.py" in cmd["args"]


def test_route_guard_scripts_exist():
    assert (ROOT / "hooks" / "route_guard.py").is_file()
    assert (ROOT / "hooks" / "route_stop_guard.py").is_file()


def test_cross_lane_hook_script_exists():
    """plugin.json points at a script — that script must actually be on disk,
    otherwise the hook silently exits non-zero forever after install."""
    assert (ROOT / "hooks" / "cross_lane_emit.py").is_file()
