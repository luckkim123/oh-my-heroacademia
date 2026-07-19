"""Tag-drift guard — ports oh-my-scholar's scripts/sync_version.py check()
semantics (ci/2026-07-19-tag-guard). omha's plugin.json deliberately has no
`version` field (commit-SHA versioning, see tests/test_plugin_manifest.py),
so the anchor here is pyproject.toml's `[project].version`, cross-checked
against CHANGELOG.md's top released entry and the latest `v*` git tag.

Tag surface: the latest tag may equal the current version (post-tag) or the
previous released version (pre-tag window — right after a version bump but
before the release tag is cut, that lag is expected, not drift). Two or more
versions behind, or ahead, is real drift. No `v*` tags at all (a repo that
hasn't cut its first tag yet) skips the tag surface rather than failing.

This CLI is read-only: it reports drift, it never edits pyproject.toml or
CHANGELOG.md.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
CHANGELOG_RE = re.compile(r"^## (\d+\.\d+\.\d+)\b")
PYPROJECT_VERSION_RE = re.compile(r'^version\s*=\s*"(\d+\.\d+\.\d+)"', re.MULTILINE)


def parse_changelog(path) -> list:
    """Released version strings, top-to-bottom. Non-numeric headings (e.g. an
    `## Unreleased` section) don't match CHANGELOG_RE, so they're skipped."""
    text = Path(path).read_text(encoding="utf-8")
    return [m.group(1) for line in text.splitlines() if (m := CHANGELOG_RE.match(line))]


def parse_pyproject_version(path) -> str:
    text = Path(path).read_text(encoding="utf-8")
    m = PYPROJECT_VERSION_RE.search(text)
    return m.group(1) if m else None


def parse_tags(tags):
    """Latest exact `vMAJOR.MINOR.PATCH` tag by numeric tuple, or None."""
    best, best_tuple = None, None
    for t in tags:
        m = TAG_RE.match(t)
        if not m:
            continue
        tup = tuple(int(x) for x in m.groups())
        if best_tuple is None or tup > best_tuple:
            best, best_tuple = t, tup
    return best


def gather(repo_root) -> dict:
    repo_root = Path(repo_root)
    version = parse_pyproject_version(repo_root / "pyproject.toml")

    versions = parse_changelog(repo_root / "CHANGELOG.md")
    changelog_top = versions[0] if versions else None
    changelog_prev = versions[1] if len(versions) > 1 else None

    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "tag", "-l", "v*"],
            capture_output=True, text=True, check=True,
        ).stdout
        latest_tag = parse_tags([t for t in out.splitlines() if t.strip()])
    except (subprocess.CalledProcessError, OSError):
        latest_tag = None

    return {
        "version": version,
        "changelog_top": changelog_top,
        "changelog_prev": changelog_prev,
        "latest_tag": latest_tag,
    }


def check(version, changelog_top, changelog_prev, latest_tag) -> list:
    """Drift strings across the 3 surfaces (empty = in sync)."""
    drift = []

    if version != changelog_top:
        drift.append(f"pyproject.toml version {version} != CHANGELOG top released {changelog_top}")

    if latest_tag is not None:
        tag_version = latest_tag[1:] if latest_tag.startswith("v") else latest_tag
        if tag_version not in (version, changelog_prev):
            drift.append(
                f"latest tag {latest_tag} matches neither pyproject.toml {version} "
                f"nor previous released {changelog_prev}"
            )

    return drift


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Report version/tag drift across 3 SSOT surfaces (read-only).")
    ap.add_argument("--repo-root", default=".")
    args = ap.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()

    s = gather(repo_root)
    drift = check(s["version"], s["changelog_top"], s["changelog_prev"], s["latest_tag"])

    print(f"pyproject.toml version: {s['version']} (anchor)")
    changelog_drift = next((d for d in drift if d.startswith("pyproject.toml")), None)
    print(f"CHANGELOG top released: {'DRIFT: ' + str(s['changelog_top']) if changelog_drift else 'PASS'}")

    if s["latest_tag"] is None:
        print("latest git tag:         SKIP (no v* tags found)")
    else:
        tag_drift = next((d for d in drift if d.startswith("latest tag")), None)
        print(f"latest git tag:         {'DRIFT: ' + s['latest_tag'] if tag_drift else 'PASS'}")

    if drift:
        print("\nDrift detected:")
        for d in drift:
            print(f"  - {d}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
