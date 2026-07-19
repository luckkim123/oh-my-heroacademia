#!/usr/bin/env python3
"""Read-only diagnostic: is the code you edited actually the code your session runs?

Each om* plugin installs from the marketplace into a version-dir cache
(<cache-root>/<plugin-name>/<version>/), while a dev checkout's
.claude-plugin/plugin.json declares whatever version you just edited. The
installer only prints an advisory, never auto-updates, so the two silently
drift. This compares dev-declared version against the highest semver-named
subdir actually installed and reports IN-SYNC / DRIFT / NOT-INSTALLED per
DEV_ROOT. Never writes anything.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
_DEFAULT_CACHE_ROOT = "~/.claude/plugins/cache/heroacademia"


def _semver_key(version):
    return tuple(int(p) for p in version.split("."))


def _read_pyproject_version(pyproject_path):
    """[project].version fallback for plugin.json that omits version deliberately."""
    try:
        import tomllib
        with pyproject_path.open("rb") as f:
            return tomllib.load(f).get("project", {}).get("version")
    except ModuleNotFoundError:
        # ponytail: no tomllib on Python <3.11 (repo supports >=3.9) — a regex
        # grab of `version = "..."` is enough for this single known key, add a
        # real TOML parse if pyproject grows nested version-like keys.
        m = re.search(r'(?m)^\s*version\s*=\s*"([^"]+)"', pyproject_path.read_text())
        return m.group(1) if m else None


def read_dev_declaration(dev_root):
    """Return (name, version) declared by a dev checkout, or raise ValueError."""
    manifest = dev_root / ".claude-plugin" / "plugin.json"
    if not manifest.is_file():
        raise ValueError(f"no .claude-plugin/plugin.json under {dev_root}")
    data = json.loads(manifest.read_text())
    name = data.get("name")
    if not name:
        raise ValueError(f"plugin.json missing 'name' in {dev_root}")
    version = data.get("version")
    if version:
        return name, version
    pyproject = dev_root / "pyproject.toml"
    if pyproject.is_file():
        version = _read_pyproject_version(pyproject)
        if version:
            return name, version
    raise ValueError(f"no version in plugin.json or pyproject.toml for '{name}'")


def find_installed(cache_root, name):
    """Return (highest_semver_version_or_None, sorted_stray_dirnames) for a plugin."""
    plugin_cache = cache_root / name
    if not plugin_cache.is_dir():
        return None, []
    semvers, strays = [], []
    for child in sorted(plugin_cache.iterdir()):
        if not child.is_dir():
            continue
        (semvers if _SEMVER_RE.match(child.name) else strays).append(child.name)
    if not semvers:
        return None, strays
    return max(semvers, key=_semver_key), strays


def check_lane(dev_root, cache_root):
    """One row of the report for a single DEV_ROOT."""
    try:
        name, dev_version = read_dev_declaration(dev_root)
    except ValueError as e:
        return {"dev_root": str(dev_root), "name": None, "status": f"ERROR({e})", "strays": []}
    installed, strays = find_installed(cache_root, name)
    if installed is None:
        status = "NOT-INSTALLED"
    elif installed == dev_version:
        status = "IN-SYNC"
    else:
        status = f"DRIFT(dev {dev_version} vs installed {installed})"
    return {"dev_root": str(dev_root), "name": name, "status": status, "strays": strays}


def format_report(results):
    name_w = max([len("PLUGIN")] + [len(r["name"] or "?") for r in results])
    status_w = max([len("STATUS")] + [len(r["status"]) for r in results])
    lines = [f"{'PLUGIN':<{name_w}}  {'STATUS':<{status_w}}  STRAY DIRS"]
    lines.append("-" * len(lines[0]))
    for r in results:
        strays = ", ".join(r["strays"]) if r["strays"] else "-"
        lines.append(f"{(r['name'] or '?'):<{name_w}}  {r['status']:<{status_w}}  {strays}")
    return "\n".join(lines)


def run(dev_roots, cache_root):
    """Return (report_text, exit_code) for the given DEV_ROOTs against cache_root."""
    results = [check_lane(root, cache_root) for root in dev_roots]
    all_in_sync = all(r["status"] == "IN-SYNC" for r in results)
    return format_report(results), (0 if all_in_sync else 1)


def _expand(raw):
    return Path(os.path.expanduser(raw))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="lane_drift_check.py",
        description=__doc__.splitlines()[0],
    )
    parser.add_argument("dev_roots", nargs="+", metavar="DEV_ROOT", type=_expand,
                         help="path to a plugin dev checkout (contains .claude-plugin/plugin.json)")
    parser.add_argument("--cache-root", type=_expand, default=_expand(_DEFAULT_CACHE_ROOT),
                         help=f"marketplace cache root (default: {_DEFAULT_CACHE_ROOT})")
    args = parser.parse_args(argv)

    report, exit_code = run(args.dev_roots, args.cache_root)
    print(report)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
