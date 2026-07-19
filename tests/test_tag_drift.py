"""Tag-drift guard tests (ci/2026-07-19-tag-guard). Ports oh-my-scholar's
tests/test_version_sync.py semantics: `check()` is pure logic, testable
without a repo; `test_live_repo_surfaces_agree` is the live lock forcing
every release to keep pyproject.toml + CHANGELOG.md + the latest tag in
sync. See scripts/check_tag_drift.py for why the anchor is pyproject.toml
(not plugin.json — that surface deliberately has no version, commit-SHA
versioned per test_plugin_manifest.py)."""
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "check_tag_drift.py"
spec = importlib.util.spec_from_file_location("check_tag_drift", SCRIPT)
ctd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ctd)

ROOT = Path(__file__).parent.parent


def test_in_sync_passes():
    assert ctd.check("0.8.0", "0.8.0", "0.7.2", "v0.7.2") == []  # post-tag
    assert ctd.check("0.8.0", "0.8.0", "0.7.2", "v0.7.2") == []  # same, re-check idempotence
    assert ctd.check("0.8.0", "0.8.0", "0.7.2", None) == []      # pre-first-tag / no tags


def test_changelog_drift_detected():
    drift = ctd.check("0.8.0", "0.7.2", "0.7.1", None)
    assert drift
    assert any("0.8.0" in d and "0.7.2" in d for d in drift)


def test_tag_two_behind_is_drift():
    drift = ctd.check("0.8.0", "0.8.0", "0.7.2", "v0.6.0")
    assert drift
    assert any("v0.6.0" in d for d in drift)


def test_tag_one_behind_is_release_in_progress_ok():
    """Right after bumping pyproject.toml/CHANGELOG but before the tag is cut,
    latest_tag still equals the previous release — expected, not drift."""
    assert ctd.check("0.8.0", "0.8.0", "0.7.2", "v0.7.2") == []


def test_tag_ahead_is_drift():
    drift = ctd.check("0.8.0", "0.8.0", "0.7.2", "v0.9.0")
    assert drift
    assert any("v0.9.0" in d for d in drift)


def test_no_tags_skips_tag_surface():
    assert ctd.check("0.8.0", "0.8.0", "0.7.2", None) == []


def test_changelog_parser_skips_non_numeric_headings(tmp_path):
    p = tmp_path / "CHANGELOG.md"
    p.write_text(
        "# Changelog\n\n## Unreleased\n\n## 0.8.0 — 2026-07-19\n\n"
        "## 0.7.2 — 2026-06-17\n",
        encoding="utf-8",
    )
    versions = ctd.parse_changelog(p)
    assert versions[0] == "0.8.0"
    assert versions == ["0.8.0", "0.7.2"]


def test_tag_parse_is_exact_match():
    tags = ["v0.7.2", "v0.7.2-rc1", "x0.9.9", "v10.0"]
    assert ctd.parse_tags(tags) == "v0.7.2"


def test_pyproject_version_parse(tmp_path):
    p = tmp_path / "pyproject.toml"
    p.write_text('[project]\nname = "omha"\nversion = "0.8.0"\n', encoding="utf-8")
    assert ctd.parse_pyproject_version(p) == "0.8.0"


def test_live_repo_surfaces_agree():
    s = ctd.gather(ROOT)
    assert s["version"] == s["changelog_top"], (
        f"pyproject.toml version {s['version']!r} != "
        f"CHANGELOG top released {s['changelog_top']!r}"
    )
    if s["latest_tag"] is not None:
        tag_version = s["latest_tag"].lstrip("v")
        assert tag_version in (s["version"], s["changelog_prev"]), (
            f"latest tag {s['latest_tag']!r} matches neither version "
            f"{s['version']!r} nor previous released {s['changelog_prev']!r}"
        )


def test_cli_read_only():
    src = SCRIPT.read_text(encoding="utf-8")
    assert "write_text(" not in src
