import json

import lane_drift_check as ldc


def make_dev_root(base, dirname, name, version=None, pyproject_version=None):
    root = base / dirname
    (root / ".claude-plugin").mkdir(parents=True)
    manifest = {"name": name}
    if version is not None:
        manifest["version"] = version
    (root / ".claude-plugin" / "plugin.json").write_text(json.dumps(manifest))
    if pyproject_version is not None:
        (root / "pyproject.toml").write_text(
            f'[project]\nname = "x"\nversion = "{pyproject_version}"\n'
        )
    return root


def make_cache(base, name, versions=(), strays=()):
    cache_root = base / "cache"
    plugin_dir = cache_root / name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    for v in versions:
        (plugin_dir / v).mkdir()
    for s in strays:
        (plugin_dir / s).mkdir()
    return cache_root


def test_in_sync(tmp_path):
    dev = make_dev_root(tmp_path, "dev", "oh-my-docs", version="0.5.3")
    cache = make_cache(tmp_path, "oh-my-docs", versions=["0.5.3"])
    row = ldc.check_lane(dev, cache)
    assert row["status"] == "IN-SYNC"


def test_drift(tmp_path):
    dev = make_dev_root(tmp_path, "dev", "oh-my-docs", version="0.5.4")
    cache = make_cache(tmp_path, "oh-my-docs", versions=["0.5.3"])
    row = ldc.check_lane(dev, cache)
    assert row["status"] == "DRIFT(dev 0.5.4 vs installed 0.5.3)"


def test_not_installed_when_plugin_missing_from_cache(tmp_path):
    dev = make_dev_root(tmp_path, "dev", "oh-my-new-plugin", version="0.1.0")
    cache = make_cache(tmp_path, "some-other-plugin", versions=["1.0.0"])
    row = ldc.check_lane(dev, cache)
    assert row["status"] == "NOT-INSTALLED"


def test_not_installed_when_cache_dir_empty(tmp_path):
    dev = make_dev_root(tmp_path, "dev", "oh-my-docs", version="0.5.3")
    cache = make_cache(tmp_path, "oh-my-docs", versions=[])
    row = ldc.check_lane(dev, cache)
    assert row["status"] == "NOT-INSTALLED"


def test_stray_dirs_reported_alongside_status(tmp_path):
    dev = make_dev_root(tmp_path, "dev", "oh-my-experiments", version="0.7.3")
    cache = make_cache(
        tmp_path, "oh-my-experiments", versions=["0.7.3"],
        strays=["a1b2c3d4", "deadbeef01"],
    )
    row = ldc.check_lane(dev, cache)
    assert row["status"] == "IN-SYNC"
    assert row["strays"] == ["a1b2c3d4", "deadbeef01"]


def test_missing_version_falls_back_to_pyproject_toml(tmp_path):
    dev = make_dev_root(tmp_path, "dev", "oh-my-heroacademia", pyproject_version="0.8.0")
    cache = make_cache(tmp_path, "oh-my-heroacademia", versions=["0.8.0"])
    row = ldc.check_lane(dev, cache)
    assert row["status"] == "IN-SYNC"


def test_missing_plugin_json_reports_error_without_crashing(tmp_path):
    dev = tmp_path / "empty_dev"
    dev.mkdir()
    cache = make_cache(tmp_path, "whatever", versions=["1.0.0"])
    row = ldc.check_lane(dev, cache)
    assert row["name"] is None
    assert row["status"].startswith("ERROR(")


def test_semver_sort_is_numeric_not_lexicographic(tmp_path):
    # Lexicographic string sort would rank "0.9.0" above "0.12.2" ('9' > '1').
    make_dev_root(tmp_path, "dev", "oh-my-heroacademia", version="0.12.2")
    cache = make_cache(tmp_path, "oh-my-heroacademia", versions=["0.9.0", "0.12.2"])
    installed, _ = ldc.find_installed(cache, "oh-my-heroacademia")
    assert installed == "0.12.2"


def test_run_exit_code_0_when_all_in_sync(tmp_path):
    dev1 = make_dev_root(tmp_path, "dev1", "oh-my-docs", version="0.5.3")
    dev2 = make_dev_root(tmp_path, "dev2", "oh-my-project", version="0.6.1")
    cache_root = tmp_path / "cache"
    make_cache(tmp_path, "oh-my-docs", versions=["0.5.3"])
    make_cache(tmp_path, "oh-my-project", versions=["0.6.1"])
    report, exit_code = ldc.run([dev1, dev2], cache_root)
    assert exit_code == 0
    assert "IN-SYNC" in report


def test_run_exit_code_1_when_any_drift(tmp_path):
    dev1 = make_dev_root(tmp_path, "dev1", "oh-my-docs", version="0.5.3")
    dev2 = make_dev_root(tmp_path, "dev2", "oh-my-project", version="0.7.4")
    cache_root = tmp_path / "cache"
    make_cache(tmp_path, "oh-my-docs", versions=["0.5.3"])
    make_cache(tmp_path, "oh-my-project", versions=["0.7.3"])
    report, exit_code = ldc.run([dev1, dev2], cache_root)
    assert exit_code == 1
    assert "DRIFT(dev 0.7.4 vs installed 0.7.3)" in report


def test_run_exit_code_1_when_not_installed(tmp_path):
    dev = make_dev_root(tmp_path, "dev", "oh-my-new", version="0.1.0")
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    report, exit_code = ldc.run([dev], cache_root)
    assert exit_code == 1
    assert "NOT-INSTALLED" in report


def test_main_cli_returns_matching_exit_code(tmp_path, capsys):
    dev = make_dev_root(tmp_path, "dev", "oh-my-docs", version="0.5.3")
    cache_root = make_cache(tmp_path, "oh-my-docs", versions=["0.5.3"])
    code = ldc.main([str(dev), "--cache-root", str(cache_root)])
    assert code == 0
    out = capsys.readouterr().out
    assert "IN-SYNC" in out
