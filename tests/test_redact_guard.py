"""PreToolUse privacy backstop: redact_guard.py.

Sibling of route_guard.py — warns (never blocks) when an outgoing `gh pr
create`/`gh pr edit` Bash call or a `mcp__github__create_pull_request` /
`mcp__github__create_or_update_file` MCP call matches a line in the
user-maintained, gitignored `.omha/redact-patterns.txt` denylist. Naming only
the pattern's line index in the warning, never the matched text itself.

Test groups mirror route_guard/cross_lane_emit's convention:
  1. load_patterns — denylist file -> literal lowercase patterns
  2. find_match — pattern index lookup (never leaks matched text)
  3. extract_payload — tool call -> scannable text, out-of-scope -> None
  4. run() e2e — stdin dict -> warn envelope or None
  5. fail-open — missing file / malformed stdin / bad tool_input never blocks
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))
import redact_guard as rdg


# ─── group 1: load_patterns ──────────────────────────────────────────────────

def _write_denylist(tmp_path, text):
    d = tmp_path / ".omha"
    d.mkdir()
    (d / "redact-patterns.txt").write_text(text)


def test_load_patterns_reads_literal_lines(tmp_path):
    _write_denylist(tmp_path, "my-private-codename\nexample-ssh-alias\n")
    assert rdg.load_patterns(str(tmp_path)) == ["my-private-codename", "example-ssh-alias"]


def test_load_patterns_ignores_comments_and_blank_lines(tmp_path):
    _write_denylist(tmp_path, "# a comment\n\nreal-pattern\n   \n")
    assert rdg.load_patterns(str(tmp_path)) == ["real-pattern"]


def test_load_patterns_lowercases_for_case_insensitive_match(tmp_path):
    _write_denylist(tmp_path, "MixedCase-Pattern\n")
    assert rdg.load_patterns(str(tmp_path)) == ["mixedcase-pattern"]


def test_load_patterns_missing_file_returns_empty(tmp_path):
    assert rdg.load_patterns(str(tmp_path)) == []


# ─── group 2: find_match ──────────────────────────────────────────────────────

def test_find_match_returns_one_based_index():
    assert rdg.find_match("has my-private-codename in it", ["nope", "my-private-codename"]) == 2


def test_find_match_case_insensitive():
    assert rdg.find_match("has MY-PRIVATE-CODENAME in it", ["my-private-codename"]) == 1


def test_find_match_none_when_no_pattern_hits():
    assert rdg.find_match("nothing sensitive here", ["my-private-codename"]) is None


def test_find_match_none_on_empty_text():
    assert rdg.find_match("", ["anything"]) is None


# ─── group 3: extract_payload — scope + field extraction ────────────────────

def test_bash_gh_pr_create_extracted():
    cmd = "gh pr create --title x --body y"
    assert rdg.extract_payload("Bash", {"command": cmd}) == cmd


def test_bash_gh_pr_edit_extracted():
    cmd = "gh pr edit 42 --body y"
    assert rdg.extract_payload("Bash", {"command": cmd}) == cmd


def test_bash_non_gh_pr_command_out_of_scope():
    """Matcher should already exclude this, but the function defends itself too."""
    assert rdg.extract_payload("Bash", {"command": "gh issue list"}) is None
    assert rdg.extract_payload("Bash", {"command": "ls -la"}) is None


def test_mcp_create_pull_request_joins_title_and_body():
    payload = rdg.extract_payload(
        "mcp__github__create_pull_request", {"title": "t", "body": "b"})
    assert "t" in payload and "b" in payload


def test_mcp_create_or_update_file_extracts_content():
    payload = rdg.extract_payload(
        "mcp__github__create_or_update_file", {"content": "some file content"})
    assert "some file content" in payload


def test_unhandled_tool_returns_none():
    assert rdg.extract_payload("Read", {"file_path": "/x"}) is None


def test_missing_tool_input_keys_returns_none_ish():
    """No title/body/content -> joined empty string, treated as 'nothing to scan'
    by run() (empty string is falsy)."""
    assert rdg.extract_payload("mcp__github__create_pull_request", {}) == ""


# ─── group 4: run() e2e ───────────────────────────────────────────────────────

def test_e2e_match_fires_warning_names_only_line_index(tmp_path):
    _write_denylist(tmp_path, "nope\nmy-private-codename\n")
    stdin_obj = {
        "tool_name": "Bash",
        "tool_input": {"command": "gh pr create --title x --body 'has my-private-codename in it'"},
        "cwd": str(tmp_path),
    }
    out = rdg.run(stdin_obj)
    assert out is not None
    msg = out["hookSpecificOutput"]["additionalContext"]
    assert "line 2" in msg
    assert "my-private-codename" not in msg  # never echo the matched text itself


def test_e2e_no_denylist_file_allows(tmp_path):
    stdin_obj = {
        "tool_name": "Bash",
        "tool_input": {"command": "gh pr create --title x --body y"},
        "cwd": str(tmp_path),
    }
    assert rdg.run(stdin_obj) is None


def test_e2e_no_match_allows(tmp_path):
    _write_denylist(tmp_path, "my-private-codename\n")
    stdin_obj = {
        "tool_name": "Bash",
        "tool_input": {"command": "gh pr create --title x --body y"},
        "cwd": str(tmp_path),
    }
    assert rdg.run(stdin_obj) is None


def test_e2e_out_of_scope_tool_allows(tmp_path):
    _write_denylist(tmp_path, "my-private-codename\n")
    stdin_obj = {
        "tool_name": "Bash",
        "tool_input": {"command": "echo my-private-codename"},
        "cwd": str(tmp_path),
    }
    assert rdg.run(stdin_obj) is None  # not `gh pr create`/`edit` -> out of scope


def test_e2e_mcp_create_pull_request_matches(tmp_path):
    _write_denylist(tmp_path, "my-private-codename\n")
    stdin_obj = {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"title": "fix", "body": "touches my-private-codename"},
        "cwd": str(tmp_path),
    }
    out = rdg.run(stdin_obj)
    assert out is not None
    assert "line 1" in out["hookSpecificOutput"]["additionalContext"]


# ─── group 5: fail-open ──────────────────────────────────────────────────────

def test_failopen_malformed_stdin_object():
    """run() only ever receives a dict from main(), but defends itself against
    a missing/odd shape anyway."""
    assert rdg.run({}) is None


def test_failopen_non_dict_tool_input(tmp_path):
    _write_denylist(tmp_path, "my-private-codename\n")
    stdin_obj = {"tool_name": "Bash", "tool_input": "not-a-dict", "cwd": str(tmp_path)}
    assert rdg.run(stdin_obj) is None


def test_failopen_main_malformed_json(monkeypatch, capsys):
    """main() reads garbage JSON from stdin -> exit 0, no output, never raises."""
    import io
    monkeypatch.setattr(sys, "stdin", io.StringIO("{ not json"))
    code = rdg.main()
    assert code == 0
    assert capsys.readouterr().out == ""


def test_failopen_unreadable_cwd_never_raises(tmp_path):
    """cwd pointing at a file (not a dir) -> load_patterns degrades to [] rather
    than raising, and run() still returns None."""
    bogus_cwd = tmp_path / "not_a_dir"
    bogus_cwd.write_text("x")
    stdin_obj = {
        "tool_name": "Bash",
        "tool_input": {"command": "gh pr create --title x --body y"},
        "cwd": str(bogus_cwd),
    }
    assert rdg.run(stdin_obj) is None
