import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

import route_guard as rg
import route_log
import route_stop_guard as rsg


def _transcript(tmp_path, prompt="라우팅 로그 붙여줘", assistant=None):
    """A minimal transcript: one real user turn plus optional assistant text."""
    lines = [{"type": "user", "uuid": "turn-1",
              "message": {"content": [{"type": "text", "text": prompt}]}}]
    if assistant is not None:
        lines.append({"type": "assistant",
                      "message": {"content": [{"type": "text", "text": assistant}]}})
    p = tmp_path / "transcript.jsonl"
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    return str(p)


# ─── lane extraction ──────────────────────────────────────────────────────────

def test_lanes_in_reads_the_emitted_gfm_form():
    assert route_log.lanes_in("> **ROUTE →** oh-my-project · 구조 문제") == ["oh-my-project"]
    assert route_log.lanes_in("ROUTE: handle-directly") == ["handle-directly"]
    assert route_log.lanes_in("ROUTE -> oh-my-docs") == ["oh-my-docs"]


def test_lanes_in_counts_a_mid_turn_reroute():
    """2개 이상 = 턴 도중 재라우팅. 재라우팅 게이트가 실제로 발동했는지의 유일한 관측점."""
    text = ("> **ROUTE →** handle-directly · 단순 조회\n"
            "...본문...\n"
            "> **ROUTE →** oh-my-claudecode · 조사로 판명, 재판정")
    assert route_log.lanes_in(text) == ["handle-directly", "oh-my-claudecode"]


def test_lanes_in_ignores_prose_route():
    """'the best route through the code' 같은 산문이 판정으로 잡히면 안 된다."""
    assert route_log.lanes_in("we picked the fastest route through the parser") == []
    assert route_log.lanes_in("") == []


# ─── opt-in by directory ──────────────────────────────────────────────────────

def test_logging_is_off_until_the_directory_exists(tmp_path):
    """플러그인 훅은 사용자가 여는 모든 repo 에서 돈다 — 조용히 dot-dir 를 만들지 않는다."""
    assert route_log.log_dir(str(tmp_path)) is None
    assert route_log.record(str(tmp_path), "turn-1", "ROUTE: handle-directly", "hi") is None
    assert not (tmp_path / ".omha").exists(), "logger must not create the directory"


def test_record_appends_one_line_when_enabled(tmp_path):
    (tmp_path / ".omha").mkdir()
    route_log.record(str(tmp_path), "turn-1", "> **ROUTE →** oh-my-docs · 문서", "만들어줘")
    route_log.record(str(tmp_path), "turn-2", "no verdict here", "또 뭐")
    lines = (tmp_path / ".omha" / "routing.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2
    first, second = json.loads(lines[0]), json.loads(lines[1])
    assert first["lanes"] == ["oh-my-docs"] and first["missing"] is False
    assert first["prompt"] == "만들어줘" and first["turn_id"] == "turn-1"
    assert second["missing"] is True and second["lanes"] == []


def test_record_flags_reroute_and_analyze(tmp_path):
    (tmp_path / ".omha").mkdir()
    window = ("> **ANALYZE**\n> - **목적**: x\n"
              "> **ROUTE →** superpowers · a\n...\n> **ROUTE →** oh-my-project · b")
    route_log.record(str(tmp_path), "t", window, "p")
    rec = json.loads((tmp_path / ".omha" / "routing.jsonl").read_text().strip())
    assert rec["rerouted"] is True and rec["analyze"] is True
    assert rec["lanes"] == ["superpowers", "oh-my-project"]


def test_record_is_valid_jsonl_with_korean_intact(tmp_path):
    (tmp_path / ".omha").mkdir()
    route_log.record(str(tmp_path), "t", "ROUTE: handle-directly", "한글 프롬프트")
    raw = (tmp_path / ".omha" / "routing.jsonl").read_text()
    assert "한글 프롬프트" in raw, "ensure_ascii=False 라야 사람이 읽을 수 있다"
    assert json.loads(raw)["prompt"] == "한글 프롬프트"


# ─── prompt extraction ────────────────────────────────────────────────────────

def test_turn_prompt_reads_the_opening_user_message(tmp_path):
    t = _transcript(tmp_path, prompt="훅은 요약만 남겨줘", assistant="> **ROUTE →** handle-directly · x")
    assert route_log.turn_prompt(t, rg._is_real_user_turn) == "훅은 요약만 남겨줘"


def test_turn_prompt_truncates_and_collapses_whitespace(tmp_path):
    t = _transcript(tmp_path, prompt="가" * 500 + "\n\n  꼬리")
    got = route_log.turn_prompt(t, rg._is_real_user_turn)
    assert len(got) == route_log.PROMPT_EXCERPT
    assert "\n" not in got


def test_turn_prompt_survives_a_corrupt_line(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text('{"broken\n' + json.dumps(
        {"type": "user", "uuid": "u", "message": {"content": [{"type": "text", "text": "ok"}]}}) + "\n")
    assert route_log.turn_prompt(str(p), rg._is_real_user_turn) == "ok"


def test_turn_prompt_returns_empty_for_a_missing_file():
    assert route_log.turn_prompt("/nonexistent/transcript.jsonl", rg._is_real_user_turn) == ""


# ─── wiring into the Stop hook ────────────────────────────────────────────────

def test_log_turn_writes_through_the_stop_hook(tmp_path):
    (tmp_path / ".omha").mkdir()
    t = _transcript(tmp_path, prompt="ㄱㄱ", assistant="> **ROUTE →** oh-my-project · 구조")
    rsg.log_turn({"transcript_path": t, "cwd": str(tmp_path), "session_id": "s"})
    rec = json.loads((tmp_path / ".omha" / "routing.jsonl").read_text().strip())
    assert rec["lanes"] == ["oh-my-project"] and rec["prompt"] == "ㄱㄱ"


def test_log_turn_records_the_turn_that_skipped_its_route(tmp_path):
    """ROUTE 를 빠뜨린 턴이야말로 이 파일에서 제일 중요한 레코드다 — 게이트 판정과
    무관하게 기록돼야 한다."""
    (tmp_path / ".omha").mkdir()
    t = _transcript(tmp_path, prompt="뭐 하나만", assistant="그냥 답만 씁니다")
    rsg.log_turn({"transcript_path": t, "cwd": str(tmp_path), "session_id": "s"})
    rec = json.loads((tmp_path / ".omha" / "routing.jsonl").read_text().strip())
    assert rec["missing"] is True


def test_log_turn_records_the_session_id(tmp_path):
    """usage.jsonl 과 이을 조인 키. 없으면 레인별 비용을 내려면 프로젝트의 트랜스크립트를
    전수 스캔해야 한다 — turn_id 가 트랜스크립트 uuid 라 조인 자체는 되지만 비싸다."""
    (tmp_path / ".omha").mkdir()
    t = _transcript(tmp_path, prompt="현황", assistant="> **ROUTE →** oh-my-project · x")
    rsg.log_turn({"transcript_path": t, "cwd": str(tmp_path), "session_id": "sess-42"})
    rec = json.loads((tmp_path / ".omha" / "routing.jsonl").read_text().strip())
    assert rec["session_id"] == "sess-42"


def test_session_id_field_is_always_present(tmp_path):
    """빈 문자열로라도 항상 있어야 한다 — 필드 부재와 미지 세션을 구분하지 못하면
    집계기가 두 경우를 같은 것으로 센다."""
    (tmp_path / ".omha").mkdir()
    t = _transcript(tmp_path, prompt="현황", assistant="> **ROUTE →** handle-directly · x")
    rsg.log_turn({"transcript_path": t, "cwd": str(tmp_path)})   # session_id 없음
    rec = json.loads((tmp_path / ".omha" / "routing.jsonl").read_text().strip())
    assert rec["session_id"] == ""


def test_log_turn_never_raises(tmp_path):
    """로거는 어떤 입력에도 세션을 깨뜨리면 안 된다 (fail-open)."""
    assert rsg.log_turn({}) is None
    assert rsg.log_turn({"transcript_path": "/nope.jsonl", "cwd": str(tmp_path)}) is None
    assert rsg.log_turn({"transcript_path": _transcript(tmp_path), "cwd": None}) is None


def test_load_dedupes_a_turn_that_was_sent_back_for_its_route(tmp_path):
    """Stop 게이트는 ROUTE 를 빠뜨린 턴에 두 번 발화한다 — 두 레코드를 다 세면
    누락률이 실제의 약 두 배로 보고된다. 마지막 레코드만 유효하다."""
    (tmp_path / ".omha").mkdir()
    route_log.record(str(tmp_path), "t1", "답만 씀", "p1")                    # 1차: 누락
    route_log.record(str(tmp_path), "t1", "> **ROUTE →** handle-directly · x", "p1")  # 재발화
    route_log.record(str(tmp_path), "t2", "> **ROUTE →** oh-my-docs · y", "p2")
    recs = route_log.load(tmp_path / ".omha" / "routing.jsonl")
    assert len(recs) == 2
    s = route_log.summarize(recs)
    assert s["turns"] == 2 and s["missing"] == 0
    assert s["lanes"] == {"handle-directly": 1, "oh-my-docs": 1}


def test_load_returns_empty_for_a_missing_file(tmp_path):
    assert route_log.load(tmp_path / "nope.jsonl") == []


# ─── 회전 ─────────────────────────────────────────────────────────────────────

def _fill(path, n_bytes):
    """유효한 jsonl 로 파일을 n_bytes 이상 채운다 — load() 가 읽어야 하므로."""
    with open(path, "a", encoding="utf-8") as f:
        while path.stat().st_size <= n_bytes:
            f.write(json.dumps({"turn_id": f"old-{path.stat().st_size}",
                                "lanes": ["handle-directly"], "pad": "x" * 300}) + "\n")
            f.flush()


def test_record_rotates_once_the_live_file_passes_the_cap(tmp_path):
    """무한히 자라는 append 로그는 동기화 폴더에서 턴마다 전체를 업로드하게 만든다.
    상한을 넘으면 라이브 파일은 `.1` 로 밀려나고 새로 시작해야 한다."""
    (tmp_path / ".omha").mkdir()
    live = tmp_path / ".omha" / "routing.jsonl"
    _fill(live, route_log.MAX_BYTES)
    big = live.stat().st_size

    route_log.record(str(tmp_path), "t-new", "> **ROUTE →** oh-my-docs · x", "p")

    assert (tmp_path / ".omha" / "routing.jsonl.1").stat().st_size == big
    assert live.stat().st_size < big          # 새로 시작했다
    assert json.loads(live.read_text().strip())["turn_id"] == "t-new"


def test_record_does_not_rotate_below_the_cap(tmp_path):
    """상한 아래에서는 회전이 없어야 한다 — 매 턴 회전하면 창이 1 줄로 줄어든다."""
    (tmp_path / ".omha").mkdir()
    route_log.record(str(tmp_path), "t1", "ROUTE: handle-directly", "p1")
    route_log.record(str(tmp_path), "t2", "ROUTE: oh-my-docs", "p2")
    assert not (tmp_path / ".omha" / "routing.jsonl.1").exists()
    assert len(route_log.load(tmp_path / ".omha" / "routing.jsonl")) == 2


def test_load_reads_the_rotated_generation_too(tmp_path):
    """회전 순간 분석 창이 조용히 무너지면 안 된다 — 두 세대를 다 읽어야 한다."""
    (tmp_path / ".omha").mkdir()
    live = tmp_path / ".omha" / "routing.jsonl"
    route_log.record(str(tmp_path), "t-old", "> **ROUTE →** oh-my-project · x", "p-old")
    _fill(live, route_log.MAX_BYTES)
    route_log.record(str(tmp_path), "t-new", "> **ROUTE →** oh-my-docs · y", "p-new")

    ids = {r["turn_id"] for r in route_log.load(live)}
    assert "t-old" in ids and "t-new" in ids


def test_load_prefers_the_live_record_of_a_turn_that_straddles_a_rotation(tmp_path):
    """Stop 게이트 재발화가 회전을 사이에 두고 갈리면, 살아남을 건 나중 것이다.
    회전본을 나중에 읽으면 누락 레코드가 정정 레코드를 덮어쓴다."""
    (tmp_path / ".omha").mkdir()
    live = tmp_path / ".omha" / "routing.jsonl"
    route_log.record(str(tmp_path), "t1", "답만 씀", "p1")          # 1차: ROUTE 누락
    _fill(live, route_log.MAX_BYTES)
    route_log.record(str(tmp_path), "t1", "ROUTE: handle-directly", "p1")   # 정정

    rec = [r for r in route_log.load(live) if r["turn_id"] == "t1"][0]
    assert rec["missing"] is False and rec["lanes"] == ["handle-directly"]


def test_rotation_keeps_only_one_generation(tmp_path):
    """두 번째 회전은 앞 회전본을 덮어쓴다 — 아무도 안 읽는 세대를 쌓지 않는다."""
    (tmp_path / ".omha").mkdir()
    live = tmp_path / ".omha" / "routing.jsonl"
    for turn in ("t1", "t2"):
        _fill(live, route_log.MAX_BYTES)
        route_log.record(str(tmp_path), turn, "ROUTE: handle-directly", "p")
    assert sorted(p.name for p in (tmp_path / ".omha").iterdir()) == \
        ["routing.jsonl", "routing.jsonl.1"]


def test_a_failing_rotation_still_logs(tmp_path, monkeypatch):
    """회전이 실패해도(권한·경쟁) 로깅은 계속돼야 한다 — 로거는 fail-open 이다."""
    (tmp_path / ".omha").mkdir()
    live = tmp_path / ".omha" / "routing.jsonl"
    _fill(live, route_log.MAX_BYTES)
    monkeypatch.setattr(route_log.Path, "replace",
                        lambda *a, **k: (_ for _ in ()).throw(OSError))
    assert route_log.record(str(tmp_path), "t-new", "ROUTE: oh-my-docs", "p") is not None
    assert "t-new" in live.read_text()


def test_cli_reports_and_exits_nonzero_when_empty(tmp_path, capsys):
    assert route_log._cli(["route_log", str(tmp_path)]) == 1
    (tmp_path / ".omha").mkdir()
    route_log.record(str(tmp_path), "t", "> **ROUTE →** oh-my-project · z", "구조 정리")
    assert route_log._cli(["route_log", str(tmp_path)]) == 0
    assert "oh-my-project" in capsys.readouterr().out


def test_a_failing_logger_never_breaks_the_stop_event(tmp_path, monkeypatch):
    """로깅이 터져도 세션은 정상 종료돼야 한다.

    0.9.0 이전에는 이 테스트가 '로거가 터져도 Stop 게이트 결정은 그대로'였다.
    게이트가 route_guard(PreToolUse)로 일원화되면서 지킬 불변식이 하나 줄었다 —
    이제 남은 건 '로거는 절대 세션을 막지 않는다' 뿐이다."""
    import io
    monkeypatch.setattr(route_log, "record", lambda *a, **k: (_ for _ in ()).throw(RuntimeError))
    t = _transcript(tmp_path, prompt="p", assistant="ROUTE: handle-directly")
    monkeypatch.setattr(rsg.sys, "stdin",
                        io.StringIO(json.dumps({"transcript_path": t, "session_id": "s",
                                                "cwd": str(tmp_path)})))
    assert rsg.main() == 0
