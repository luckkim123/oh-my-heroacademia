# Changelog

## 0.10.0 — 2026-08-28
store-spec §7 stage 2 — fallback 제거. `hooks/omha_paths.py`의 읽기 헬퍼가 그동안
`new if new.exists() else legacy`로 파일 존재 여부를 봤는데, 이제는 앵커 유무만 본다:
`.hq/.anchor`가 파싱 가능하면 읽기·쓰기 모두 `.hq/`로, 없으면 여전히 `.omha/`로 — 개별
파일이 실제로 복사됐는지는 더 이상 검사하지 않는다. 쓰기 헬퍼가 갖고 있던 중간 분기
("앵커는 있지만 이 파일이 아직 안 복사됐으면 레거시로")는 stage 1이 보호하던 창이었고,
stage 2는 그 창을 닫는다고 선언한 것이다. `_read`/`_write` 둘 다 결국 같은 식
`new if has_anchor(base) else legacy`을 계산하고 있었으므로 `_resolve(base, new, legacy)`
하나로 합쳤다.

`route_log.py`의 opt-in-by-directory 계약(로깅 on/off는 앵커가 아니라 런타임 디렉터리
존재로 결정)은 이 릴리스에서 손대지 않았다 — HUB 결정 D21(2026-08-28)로 이미 확정·측정된
동작이라 fallback 제거 범위 밖.

`.gitignore`: 이 저장소 자신의 레거시 스토어 줄(`.omha/redact-patterns.txt`)을 제거했다
— `**/.hq/runtime/`가 흡수한다(store-spec §9.4). `git check-ignore -v` 전후 대조 결과
실제로 새로 tracked 되는 파일은 없었다 — 이 저장소의 `.omha/`에는 이미 tracked인
`redact-patterns.example.txt`만 있고, 실사용 파일(`redact-patterns.txt`)은 디스크 어디에도
없었다.

### Changed
- `hooks/omha_paths.py`: `_read`/`_write` → `_resolve(base, new, legacy)`로 병합.
  `redact_patterns_txt`·`routing_jsonl` 모두 이걸 통해 재계산. `gate_state()`의 `legacy`
  행 독스트링을 "warn, read via fallback"에서 "warn: 이 프로젝트는 미이주 레거시 스토어를
  갖고 있고 `.hq/`에서는 읽히지 않는다"로 정정 — 이 상태에서 더 이상 fallback은 없다.
- 모듈 독스트링을 stage 1(P4, write-new/read-both) 서술에서 stage 2 서술로 재작성.

### Fixed
- pyproject.toml이 0.9.1에 멈춰 있었던 걸 발견 — CHANGELOG는 이미 0.9.2 항목을 갖고
  있었는데(docs-only 커밋 c0809ad) 버전 파일 동기화가 빠져 있었다. 별도 정정 커밋 대신
  이번 릴리스의 점프(0.9.1 → 0.10.0)에 접어 넣기로 했고, 이 판단은 리뷰에서 확인됐다 —
  누락된 0.9.2 범프는 이렇게 기록으로 남기고, off-by-one 오류처럼 보이게 두지 않는다.

### Cards — injected routing-prose sweep
omha는 라우팅 하네스라 매 턴 주입되는 텍스트가 세션 전체에 미친다. 서브에이전트는 훅은
물려받아도 CLAUDE.md는 물려받지 않으므로, 카드 텍스트가 서브에이전트가 실제로 따르는
유일한 안내다. 스토어를 곧 purge할 예정이라, 카드가 다른 하네스의 레거시 경로를 이름으로
갖고 있으면 존재하지 않는 디렉터리를 조용히 가리키게 된다. `hooks/route_emit.py`(실제
주입기)와 `cards/*.json` 6개 전부를 훑었다 — `oms`/`omd`/`omc`/`superpowers` 카드는
레거시 경로 언급이 없었다.

바뀐 것 (경로는 `~/claudebase/runtime/bin/migrate-om-store.sh`의 `rules_for()` 매핑을
그대로 따름):
- `cards/omp.json` — description 3곳 + example 1곳: `.omp/env/` → `.hq/config/project/env/`
  (`dir|env|config/project/env`), `.omp/ SSOT` → `.hq/ SSOT`, `.omp/secretary/` →
  `.hq/config/project/secretary/` (`dir|secretary|config/project/secretary`),
  `The .omp/ index-coherence` → `The .hq/ index-coherence`.
- `cards/omx.json` — description 2곳 + example 1곳: `` `.omx/programs/<id>/PLAN.md` `` →
  `` `.hq/community/programs/<id>/PLAN.md` `` (`dir|programs|community/programs`),
  `.omx/profile analyzer` → `.hq/config/experiments/profile/ analyzer`
  (`dir|profile|config/experiments/profile`).

의도적으로 남긴 것 (경로 지시가 아니라 마크커 사용이라 판단):
- `cards/omp.json`의 `tags` 배열 안 bare `.omp` 항목, 그리고 example
  `"이 프로젝트 폴더 스캔해서 .omp 초기화해줘 (init)"` — 둘 다 슬래시·하위경로가 없는
  bare mnemonic이라 특정 디렉터리를 가리키지 않는다(트리거 키워드/사용자 발화 예시).
- `skills/routing/SKILL.md:25`의 `.omp 규칙?` — 같은 이유.
- `skills/routing/SKILL.md:142`의 "찾는 순서는 `.hq/runtime/routing/` → 구 `.omha/`" —
  route_log의 opt-in-by-directory 메커니즘을 정확히 서술하는 문장이라 "미이주 레거시
  스토어에 관한 서술" 예외에 해당(D21, 손대지 않음).

**실제 주입 char delta: 0.** `route_emit.py`의 `_digest()`는 레인당 240자에서 자르는데,
수정한 문자열은 둘 다 잘리는 지점(omp 239자, omx 232자) 훨씬 뒤(전체 설명문 700자대
이후)에 있다 — 오늘 시점엔 세션 프롬프트에 주입된 적이 애초에 없었다. `cross_lane_emit.py`는
`description`/`tags`/`examples`를 아예 안 읽는다(트리거의 `extensions`/`skills`만). 그래도
소스 콘텐츠 자체는 고쳤다 — description 앞부분이 조금만 짧아져도 digest 경계가 이 문자열
쪽으로 옮겨올 수 있는 우연한 컷오프라서.

### Audited — attribute-shaped legacy roots (widened sweep)
oh-my-experiments 쪽에서 `compact_breadcrumb()`가 `paths.omx_dir`(레거시 경로로 굳은
속성)를 직접 glob해 getter를 안 거치는 결함을 찾았다는 보고를 받고, 같은 모양이
이 저장소에도 있는지 별도로 훑었다. 인용부호 문자열 grep으로는 이 모양(속성/상수를
통한 우회)이 안 잡혀서 별도 검사가 필요했다.

`grep -rn "legacy_root\|LEGACY_ROOT\|omha_dir" hooks/ scripts/ src/` 전체 결과와 판정:
- `hooks/omha_paths.py:49` `LEGACY_ROOT = ".omha"` — 단일 선언 지점 그 자체. (b) 정당.
- `hooks/omha_paths.py:64` `root()` 함수 정의(`Path(base) / LEGACY_ROOT`) — 이 저장소엔
  `omha_dir` 같은 bare 속성이 아예 없다: 레거시 루트는 항상 `root(base)` **함수 호출**을
  통해서만 얻어진다. (b) 정당.

`root(` 호출 전체(정의 제외 4곳) 각각의 판정:
- `omha_paths.py:141` `has_legacy_store()` = `root(base).is_dir()` — (b) 정당한 레거시
  감지 그 자체(게이트의 `legacy`/`has_legacy_store` 판정용).
- `omha_paths.py:192`, `:199` `redact_patterns_txt()`/`routing_jsonl()`이 `_resolve()`에
  넘기는 `legacy` 인자 — (a) 읽기/쓰기 경로, 이미 `_resolve()`를 통해 정상 해석됨(이번
  릴리스에서 고친 부분).
- `route_log.py:101` `log_dir()`의 `legacy = omha_paths.root(cwd)` — **`routing_jsonl()`을
  안 거치지만 하드코딩된 속성도 아니다.** `omha_paths.root()`/`omha_paths.runtime_dir()`
  라는 정식 getter *함수*를 그대로 호출하고 있고, `_resolve()`를 안 쓰는 건 의도된 것 —
  옵트인 여부는 앵커가 아니라 "그 디렉터리가 이미 존재하는가"로 결정해야 하기 때문에
  (opt-in-by-directory, D21), 앵커 기반 `_resolve()`를 쓰면 이 계약 자체가 깨진다.
  결론: **resolution bug 아님.** oh-my-experiments의 `paths.omx_dir` 결함과 모양이 다르다
  — 거긴 getter를 아예 거치지 않는 하드코딩 속성이었고, 여긴 getter 함수를 거치되 다른
  (하지만 올바른) 결정 규칙을 쓴다. (b) 정당 — 손대지 않음.
- redact-patterns 경로도 동일하게 확인: `redact_guard.py:50`이 부르는 곳은
  `omha_paths.redact_patterns_txt(cwd)` 단 한 곳뿐이고, 이건 이미 `_resolve()`를 거친다.
  우회 경로 없음.

`scripts/`(check_tag_drift.py, lane_drift_check.py)와 `src/omha/registry.py`는 legacy
루트를 전혀 참조하지 않는다 — 유일한 `.glob(`은 `cards/*.json`을 도는 것으로 스토어와
무관. `breadcrumb`/`compact`/`clean`/`gc`/`prune`류 훅도 이 저장소엔 없다(`route_guard.py`
매치는 Claude Code의 `/compact` 커맨드 관련 주석일 뿐).

**결론: 이 저장소엔 omx류 attribute-shaped 결함이 없다.** 레거시 루트로 가는 모든 경로가
`root()` 함수 하나로 수렴하고, 그 4개 호출 지점은 전부 (a) 이미 `_resolve()`로 해석되거나
(b) 의도된 레거시 감지/옵트인 메커니즘이다.

### Tests
- `tests/test_omha_store_cutover.py`: `_write` 참조를 `_resolve`로 갱신. stage 1의
  middle-branch 가정을 검증하던 테스트(anchored-but-not-copied-yet)를 stage 2에서는
  거짓이 된 주장이라 제거하고, 정반대 결과를 직접 검증하는 신규 테스트로 교체했다:
  (a) 앵커 있음 + 레거시 파일만 존재 → `.hq/` 경로 반환, (b) 앵커 없음 + 레거시 파일
  존재 → 레거시 경로 반환.
- `tests/test_card_triggers.py`, `tests/test_cross_lane_emit.py`의 "legacy" 언급은
  스토어와 무관한 픽스처 이름(카드 fixture data)임을 확인 — 변경 없음.
- `tests/test_omha_paths_lint.py` 그대로 통과 — docstring 안의 `.omha`/`.hq` 언급은
  lint 예외(첫 statement인 docstring Constant는 스캔 대상에서 빠진다).

## 0.9.2 — 2026-08-28
라우팅 판정 로그의 경로 서술이 낡아 있었다. 실제 코드는
`.hq/runtime/routing/` → 구 `.omha/` 순으로 찾는데(`route_log.log_dir`),
`skills/routing/SKILL.md` 와 `hooks/route_log.py` 의 독스트링은 둘 다 여전히
"`.omha/` 가 있으면 켜진다"고만 적고 있었다. 코드는 옳고 서술만 낡은 경우라
동작 변경은 없다 — 문장만 고쳤다.

같이 명시한 것: **앵커만 있고 런타임 디렉터리가 없으면 로깅은 안 켜진다.**
`.hq/.anchor` 는 omp·oms·omd 때문에도 서므로, 앵커를 opt-in 신호로 읽으면
사용자가 켠 적 없는 프롬프트 발췌 수집이 시작된다. 이건 `omha_paths` 의 모듈
독스트링이 이미 규정한 계약인데 사용자가 읽는 층에는 안 적혀 있었다.

`cards/omp.json` 의 omp 버전을 0.15.0 으로 맞췄다 (omp 의 `sync_version.py`
가 이 카드를 네 번째 SSOT 로 검사한다).

## 0.9.1 — 2026-08-23
게이트가 이미 선언된 ROUTE 를 못 보고 툴콜을 거부하는 일이 한 세션에서 **9회** 났다.
거부 1건은 모델 왕복 한 번을 통째로 버리는 비용이라, 0.9.0 이 검증을 실작업 턴에
몰아넣은 직후에 특히 비싸다.

원인을 추측하지 않고 재현했다 — 그 세션 트랜스크립트를 각 거부 지점에서 잘라
`route_guard._scan_turn` 을 다시 돌렸다. 두 가지가 갈렸다.

**(1) flush 레이스, 9건 중 7건.** 사후 재현하면 창에 ROUTE 가 **실재한다**. 선언은
진짜였고 훅이 파일에 닿기 전에 읽었을 뿐이다. 기존 예산 3회 × 0.15초(0.30초)가 부족했다.

**(2) cross-session 레코드가 턴 경계로 잡힘, 1건.** Claude Code 는 피어 세션의 메시지와
그 전달 통지를 `type=user` + 문자열 content 로 넣는데, 이는 사람이 타이핑한 프롬프트와
구조가 같다. 그래서 `_is_real_user_turn` 이 경계로 판정하고, 그 턴이 이미 emit 한 ROUTE 가
창 밖으로 밀려난다. 실측: 이 vault 의 user-role 레코드 1,171개 중 **125개**가 이 부류다.

(나머지 1건은 `/compact` 직후 창 0자 — 정당한 차단이라 그대로 둔다.)

### Fixed
- `route_guard.run()` — flush 예산을 0.30초에서 최대 1.2초로. 다만 상한을 거의 안 쓴다:
  ROUTE 가 보이는 즉시, 그리고 **비지 않은** 창이 성장을 멈추는 즉시 빠져나온다(작가가
  따라잡았다 = 진짜 무선언). 빈 창만 상한까지 기다리는데, 툴콜 자체가 assistant 메시지의
  존재 증명이므로 빈 창은 "모델이 말 안 했다"가 아니라 "작가가 뒤처졌다"는 뜻이다.
- `route_guard._is_real_user_turn()` — `[Cross-session delivery notice]` 와
  `Another Claude session sent a message` 로 시작하는 user-role 레코드를 경계에서 제외.
  좁게 잡았다: `/compact` 등 local-command 레코드는 경계로 남는다(compact 이전 ROUTE 가
  이후를 만족시키면 안 된다). 이 두 접두사는 사용자 요청을 전혀 담지 않는 유일한
  user-role 레코드라, 제외해도 라우팅 판정을 건너뛰는 데 쓸 수 없다 — 피어는 작업을
  보고할 뿐 요청하지 못한다.

### Notes
- 게이트는 약화되지 않는다. true negative 는 여전히 거부한다. 대신 **창이 커진다** —
  같은 세션을 재현하니 피어 트래픽에 잘려 있던 턴들이 15,254자짜리 한 턴으로 다시
  합쳐지고 맨 위 ROUTE 하나가 전체를 커버했다. 이것이 옳은 의미론이다(라우팅은 *사용자*
  요청 단위로 정해지고 그 사이 사용자 요청은 없었다). 대가는 피어 메시지가 많은 긴 턴이
  선언 하나로 게이팅된다는 것.
- 테스트 194 통과(직전 190). 신규 4 + 갱신 1.

## 0.9.0 — 2026-08-23
ROUTE 선언이 매 턴 응답 맨 위를 차지했다. 같은 레인이 연속돼도 반복되는 것은 설계된 동작이었지만
— 판정을 매 턴 다시 하게 만드는 유일한 증거이자 `routing.jsonl` 의 입력 — 사람이 읽는 화면에서는
소음이다.

선언을 화면 밖으로 옮기는 길은 없다. 트랜스크립트의 thinking 블록은 본문이 **비어서** 저장되고
(실측: 최근 40개 트랜스크립트의 thinking 938개 전부 빈 문자열, `redacted_thinking` 0건),
HTML 주석은 터미널 렌더러가 감추지 않으며, 툴을 안 쓰는 순수 대화 턴에는 모델→훅 채널이 가시
텍스트뿐이다. 가시성과 검증은 같은 것이다.

바꿀 수 있는 건 *어느 턴이 선언을 요구받느냐* 였다.

### Changed
- **ROUTE 는 이제 실작업 턴에만 출력한다.** 판정은 여전히 매 턴 돌지만, 줄은 이 턴이
  `Bash·Edit·Write·Agent·Task` 중 하나를 쓸 때만 찍는다. 대화로 시작해 작업으로 넘어가면 첫
  도구 호출 시점에 찍으면 되고, PreToolUse 게이트가 정확히 거기서 요구한다.

  실측(한 vault, 트랜스크립트 25개 / 206턴): **111턴(53.9%)이 게이트 대상 도구를 하나도 안 썼다.**
  그 턴들은 파일도 안 건드리고 에이전트도 안 띄우므로 레인이 틀려도 잃을 게 없다. 실작업 턴 95개의
  레인 분포는 superpowers 43.2% · handle-directly 33.7% · 선언없음 13.7% · omc 8.4%.

### Removed
- **Stop 백스톱의 차단 동작** (`hooks/route_stop_guard.py`). 순수 대화 턴에서 ROUTE 누락을 잡아
  `{decision: block}` 으로 응답 전체를 재작성시키던 게이트다. 요구 자체가 사라졌으니 게이트도 같이
  간다. 모듈은 남는다 — `log_turn` 이 계속 `.omha/routing.jsonl` 에 기록한다. Stop 은 끝난 턴을
  보는 유일한 이벤트라 로거는 여기 있어야 한다. 102 → 66줄.

  부수 효과: `emoji_guard`(claudebase) 가 재작성을 시킨 턴이 ROUTE 누락으로 또 차단되던 연쇄가
  대화 턴에서는 끊긴다.

### Added
- **`routing.jsonl` 레코드에 `work` 필드** (`hooks/route_log.py`). 이게 없으면 대화 턴의 *정상적인*
  무선언이 전부 `missing` 으로 집계돼 누락률이 두 배 가까이 부풀고 지표가 죽는다. `summarize()` 가
  `work_turns` 와 `missing_on_work` 를 같이 내고, CLI 도 실작업 턴 기준으로 보고한다.
  `work` 필드가 없는 0.9.0 이전 레코드는 `True` 로 취급한다 — 그때는 매 턴 규칙이었으므로 그
  `missing` 은 진짜였고, `False` 로 놓으면 이전 누락 이력이 통째로 지워진다.
- `route_log.REAL_WORK_TOOLS` — route_guard 의 PreToolUse matcher 사본. 둘이 어긋나면 `work` 가
  게이트가 보지도 않은 턴을 세게 되므로 `.claude-plugin/plugin.json` 과 함께 동기 유지가 필요하다.

### Notes
- **커버리지 경계**: `Read`·`Grep`·`Glob`·MCP 도구만 쓰는 턴은 route_guard 의 matcher 밖이라
  이제 아무 게이트도 안 걸린다. 의도된 것이다 — 읽기는 아무것도 안 바꾸고, 읽은 뒤 실제로 손대는
  순간 게이트가 잡는다.
- 표시는 omc HUD 의 `route:` 세그먼트가 맡는다 (claudebase `runtime/hud/omha-route.mjs`).
  `.omha/routing.jsonl` 이 아니라 트랜스크립트를 직접 tail-스캔한다 — statusline stdin 에
  `transcript_path` 가 실려 오므로 1턴 지연도, `.omha/` opt-in 의존도 없다.
- 주입 크기 3,118 → 3,338자 (호스트 상한은 **문자** 단위다 — 0.8.5 참조).

## 0.8.5 — 2026-08-10
The routing block had been silently truncated since the 08-10 card sync: at 15,714 characters it
crossed Claude Code's inline limit for hook `additionalContext`, so the host persisted it to a file
and injected a 2 KB preview instead — **86% of the routing rules stopped reaching the model**, with
no error anywhere (the hook exits 0, a path is injected, nothing looks wrong).

The byte-budget guard did not fire because it measured the wrong unit. 21,950 B of Korean prose is
15,714 *characters*: comfortably under the 22,300 B ceiling, well over the host's character limit.

(0.8.4 was reverted before release; this ships as 0.8.5 so the number is not reused.)

### Added
- **Routing verdict log — `.omha/routing.jsonl` (`hooks/route_log.py`).** The Stop hook now appends
  one record per turn: the lanes declared (two or more means the turn re-routed mid-flight), whether
  the ROUTE line was skipped, whether ANALYZE fired, and the first 160 chars of the prompt. It runs
  independently of the gate decision, because a turn that *skipped* its ROUTE is the most
  interesting record in the file.

  **Opt-in by directory**: writes only where `.omha/` already exists — a plugin hook runs in every
  repository the operator opens, and silently creating a dot-dir in each of them is not a routing
  plugin's business. `mkdir .omha` enables it; deleting the directory disables it. There is
  deliberately no `os.getcwd()` fallback: a hook's process cwd is not the session's cwd, and
  guessing wrote a log into this repo during development.

  Read it with `python3 hooks/route_log.py <project-root>` — lane distribution, miss and re-route
  counts, and the prompts that skipped a verdict. `load()` keeps only the last record per `turn_id`,
  because the Stop gate fires twice on a turn it sent back for its ROUTE line and counting both
  would report roughly double the real miss rate.

  The point is to stop editing the cards from anecdote. Every gate added so far was argued from one
  remembered session ("this session repeatedly got X wrong"), and that is how the block reached
  15,714 chars. Whether a gate earns its tokens is now a question the data can answer.

### Fixed
- **Unit bug in the size guard (`tests/test_route_emit.py`).** `test_emitted_context_stays_under_byte_ceiling`
  → `..._char_ceiling`: asserts `len(ctx)`, not `len(ctx.encode())`. The documented host cap is
  **10,000 characters** for `additionalContext`, `systemMessage` and plain stdout alike; the guard is
  set at 4,000 because the hook is now a summary and has no reason to approach the cap. Raising it
  re-opens the silent cut.

  (An earlier draft of this entry claimed 12,537 chars had been measured to pass. That was a
  misreading: a transcript `attachment` record stores the full hook output even when the model was
  handed only the preview, so it is not evidence of delivery.)

### Changed
- **The hook is a summary + pointer; the manual moved to a skill.** `hooks/route_emit.py` now
  injects only what is needed to *make and emit* the verdict — the 7 lane values, a 240-char digest
  per lane, the cascade in one line, the output format — plus a pointer to the new
  `oh-my-heroacademia:routing` skill carrying explicit read-triggers. **15,714 → 3,118 chars
  (−80%)**, delivered whole instead of 13% of it. Over a 90-prompt session: 1,414K → 281K chars.

  `skills/routing/SKILL.md` (new) owns the cascade detail including the tier-2.5 intent gate, the
  five re-routing obligations, the ANALYZE template, and the output-order rules — loaded on demand
  instead of paid for on every prompt. Lane bodies are **not** copied into it: it points at
  `cards/*.json`, which stays the single source of truth (a copy there would be the drift the hook's
  own docstring warns about).

  The pointer carries *when to read*, not just *what exists* — five triggers (digest does not
  settle the lane / 3+ actions / before delegating or editing a harness artifact / before asserting
  a code fact or a design judgment / undecided intent). A pointer without triggers is ignored under
  momentum, which is the whole failure mode this hook exists to fight.

- **Tests follow the split.** Prose assertions for rules that moved now target `SKILL.md`, and two
  new guards keep the structure honest: `test_hook_points_at_the_skill_with_read_triggers` (the
  pointer must name the skill *and* its triggers) and `test_per_turn_block_is_a_summary_not_the_manual`
  (fails if a full card body reappears in the hook). The per-turn ceiling tightens 12,000 → **4,000
  chars** — with the detail gone there is no reason for the hook to grow, and slack invites prose
  back in.

- **`_digest` spends its whole budget.** Sentence-granular selection (drop any sentence that would
  overflow) was tried first and is wrong for these cards: several open with a short label followed
  by one ~470-char sentence carrying the entire route-here rule, so `oh-my-project` reduced to
  "Project-structure GOVERNANCE lane (a third axis …)" — a label with nothing to route on. It now
  cuts at a sentence boundary only when one falls in the last 40% of the budget, else on a word.

## 0.8.3 — 2026-08-05
An intake-side release: the cascade sorted work by *what artifact it produces*, so every lane
presupposed a decided objective. A request whose defining property is that the user has **not yet
decided what they want** matched nothing and fell to `handle-directly` by elimination.

### Added
- **Cascade tier 2.5 — the intent-crystallization gate (`hooks/route_emit.py`).** An undecided
  goal now routes to the harness built for it: `oh-my-claudecode` (deep-interview) when no options
  have been formed yet, `superpowers` (brainstorming) when two or more are already on the table and
  the work is narrowing between them. Firing is an **intersection**, mirroring the sibling
  design/validity gate: (i) the user has not decided what they want AND (ii) the answer would run as
  a multi-turn design exploration. Observed 2026-08-05 (/workspace ALBC session): an open
  research-design question ("나도 자세하게 설명하긴 좀 어려운데 … 좀 같이 논의를 해보는건
  어때?") produced `ROUTE → handle-directly` for three consecutive turns, each deepening a verdict
  the user had not asked for. Routing changed only on turn 4, when the user typed the literal
  string "deep interview" and OMC's magic-keyword hook fired — intent never triggered it, a
  keyword did. Over-pull valve exempts three cases — an explicitly-light request, a single-fact
  check, and a trivial taste judgment (variable name, formatting) — the same escape list the
  sibling gate carries.
- **Tier 2 no longer shadows tier 2.5.** The cascade is first-match top-down and tier 2 ("pick a
  work-style lane") targets the same lanes tier 2.5 routes to, so a lane picked at tier 2 would
  never reach the new gate. Tier 2 now defers explicitly when intent is undecided. This was not
  hypothetical: the same message replayed against the old block was picked up at tier 2 as
  `oh-my-experiments`.
- **The ANALYZE gate's remedy now has a goal-undecided exception.** `모호하면` → "먼저 사용자에게
  확인하라" prescribed one ad-hoc question, which contradicts tier 2.5's "hand it to the harness"
  in the same injected block. Detail ambiguity is still asked directly; an undecided *goal* now
  goes to the gate. The trigger itself was deliberately **not** hardened — it was not followed in
  the incident, and over-correcting a rule that was simply not obeyed costs every future turn.
- **`cards/omc.json` mirrors the sp exception.** Its closing sentence still fenced sp entry to
  exactly three explicit gates, which would have contradicted the sp card and the new tier sitting
  beside it in the same block. Both cards now declare the same non-gate exception, guarded by
  `test_undecided_goal_exception_is_in_both_work_style_descriptions`.
- **`handle-directly` has a positive definition** — single-fact lookup, summarizing what is
  already decided, light conversational reply, and a provisional (not settled) opinion. "Nothing
  else matched" is no longer sufficient grounds, mirroring the anti-fallthrough guard tier 0
  already had for omp.
- **`cards/omc.json` `triggers.skills` gains `deep-interview`.** The skill appeared nowhere in the
  card — description or triggers — so nothing in omha referred to it and only a literal keyword
  match could reach it. What makes it reachable is the cascade naming it; this entry makes the
  push channel in `cross_lane_emit.py` label the skill consistently with the lane that now owns it.
  Guarded by `test_omc_card_declares_deep_interview_trigger`.
- **`cards/superpowers.json` — one non-gate exception.** The injected description said to route
  here "only when the operator EXPLICITLY wants a structural discipline gate" and "Do NOT route
  here merely because … a plan is being made", while the single matching signal ("어떤 방향이
  나을지 비교 (no direction yet)") sat in `skills[].examples` — a field `route_emit` parses but
  never injects. The reachable text actively discouraged the correct routing; the undecided-goal
  case is now named in the description itself.
- **Byte-budget guard (`test_emitted_context_stays_under_byte_ceiling`).** This block is injected
  into every turn of every session, so growth is a permanent cost. Baseline 17,193 B →
  **21,950 B** (+2,630 B design/validity gate, +2,127 B this fix); ceiling **22,300 B**, i.e.
  350 B of headroom, so the next card edit that grows the block has to decide what to cut. The
  guard earned its keep twice during development — it went red after the review fixes and again
  after the automated-review fixes, and both times the answer was to cut prose, not raise the
  ceiling.

### Changed
- **`hooks/route_emit.py` — design/validity self-approval gate.** Cherry-picked from
  `exp/handle-directly-overuse-fix` (authored 2026-07-09, never merged, and — unlike what that
  branch's tip suggested — never pushed; it existed only in one local clone). Value/validity
  *arguments* ("is this design sound / academically meaningful") are not code-fact lookups, so
  they slipped past the code-fact gate, fell to `handle-directly`, and one context authored an
  argument and approved it. It is the **output** side of the same defect family this release
  fixes on the **input** side, and it edits the same region of the cascade — carrying it here
  keeps one coherent `handle-directly` definition instead of two conflicting ones.

### Decisions
- **Fix delivered as cascade prose + two card edits, NOT by injecting `skills[].examples` /
  `triggers.skills` in `build_routing_context`.** Injecting those fields would fix the
  root cause structurally (only `description` reaches the session) and benefit every future card,
  but it pays the cost on all six cards, on every turn, forever — ~60 example strings to reach
  one. Naming the destination once in the cascade costs 1,859 B and closes the same case. The
  structural option stays open if a second card ever needs its examples in reach.
- **What was cut to pay for the new prose: two rationale clauses (~175 B), and nothing else.** An
  over-engineering review pass removed "미결정 목표 위에 쌓은 결론은 요청받지 않은 산출물이다"
  from the cascade and "a verdict produced against an undecided goal is the failure mode this
  closes" from the sp card — both explained *why* without instructing *what*, at permanent
  per-turn cost. No further offset was taken, and that is a decision rather than an oversight: the
  remaining duplication in the block (the ROUTE format spec appearing three times) is the
  anti-truncation placement `test_route_format_spec_lands_in_head_before_card_bodies` exists to
  protect, and consolidating two sibling gates' valves would rewrite load-bearing text from earlier
  incident fixes inside an unrelated release. The tightened ceiling carries that debt instead.
- **Branched from `main`, not from `exp/handle-directly-overuse-fix`.** That branch is 1 commit
  ahead and **38 behind** (it predates 0.8.1/0.8.2, CI, ruff, LICENSE, `redact_guard.py`) — its
  earlier commits were already merged at `876393d`, and building on it would have reverted a
  month of main. The one commit worth keeping was cherry-picked instead (see Changed).
- **Out of scope, recorded not fixed:** OMC's magic-keyword matcher fires on literal phrases only
  (`[MAGIC KEYWORD: DEEP-INTERVIEW]`). Whether it should do intent detection belongs to the OMC
  plugin, not omha.

### Verification
- Suite: 163 passed, 1 pre-existing unrelated failure (`test_card_sync.py::…[oh-my-docs]` — local
  sibling-clone version drift, fails identically on clean `main`; CI skips it). `ruff check .` clean,
  `check_tag_drift.py` PASS.
- Both new behavioral tests were watched failing on the pre-fix tree — that failure *is* the
  reproduction of the defect. The card-level tests were mutation-checked (removing the trigger,
  padding a card description) and each fails its guard.
- Reviewed independently before merge (correctness lens + over-engineering lens), verdict REQUEST
  CHANGES on the first round; all three blocking findings are folded in above (ANALYZE remedy
  contradiction, the omc mirror sentence, and a self-confirming negative control), plus the
  intersection valve and the tier-2 shadowing clause.
- A second automated review round on the PR caught two more contradictions, both fixed: the card
  descriptions still sent every undecided goal to brainstorming after the cascade split had been
  rewritten around whether options exist (they now carry the same split), and the `handle-directly`
  preamble stated the design/validity gate as a single condition while the gate itself requires the
  intersection (the preamble now names both conditions).
- Replay (a model reading the emitted block verbatim, one isolated session per case — there is no
  request classifier in this repo, so "request X routes to lane Y" is not unit-testable):

  | probe | routed to | via |
  |:--|:--|:--|
  | the incident's verbatim turn-1 message | `oh-my-claudecode` (deep-interview) | tier 2.5 — cited "no options formed yet" |
  | `"이 상수 값이 뭐야"` | `handle-directly` | single-fact lookup exception |
  | `"이 변수명 어떻게 생각해?"` | `handle-directly` | tier-2.5 valve, trivial taste judgment |
  | `"latent dim 9→12 어떻게 생각해?"` | `oh-my-claudecode` | design/validity gate (pre-existing) |
  | `"koopman lifting이 우리 encoder latent랑 비슷해? 어떻게 생각해?"` | `oh-my-claudecode` | research-delegation obligation (pre-existing) |

  Tier 2.5 over-pulled in **none** of the four control probes — it fired only on the genuinely
  undecided goal. Two controls did leave `handle-directly`, but through gates that predate this
  release, which is worth stating plainly: the block as a whole is aggressive about pulling
  opinion-shaped questions out of `handle-directly`, and that property is not new in 0.8.3.
  Second caveat, stated rather than buried: the incident message replayed against the **old** block
  routed `oh-my-experiments`, not the `handle-directly` the live session actually emitted. A
  single-shot replay has no conversation history and runs a different model, so it does not
  reproduce the original failure — the replay evidence covers the new block only, not a
  before/after delta. The mechanical before/after delta is the two behavioral tests failing on the
  pre-fix tree.

## 0.8.2 — 2026-08-04
### Changed
- **`cards/omx.json` claims experiment PLANNING, not just analysis/design.** The lane
  description and tags now cover a multi-stage experiment-line plan, and state explicitly
  that a plan grown from a research document rather than a `report.md` still routes here —
  the missing report is not a reason to fall through to superpowers and write into
  `.sp/plans/`. Observed 2026-08-04: a Koopman experiment plan landed in the superpowers
  scratch tree because the card described only "analyze results / design the next
  experiment", leaving research-driven planning unclaimed by any lane.
- **`cards/omx.json` version 0.9.0 -> 0.10.0**, tracking the sibling
  `oh-my-experiments` release that makes `program-init` reachable before a program's
  first campaign exists (`test_card_sync.py` requires the card and the sibling
  `plugin.json` to carry the same version).

## 0.8.1 — 2026-07-19
### Added
- **`tests/test_card_sync.py`** — local-developer drift gate comparing each `cards/<name>.json`
  (`version`, `triggers.skills`) against the matching sibling `oh-my-*` repo's live
  `.claude-plugin/plugin.json` (`version`, `skills[]`), for every card whose `name` starts with
  `"oh-my-"` except `THIRD_PARTY_CARDS = {"oh-my-claudecode"}` (marketplace-installed, unrelated
  versioning scheme). Skips cleanly wherever a sibling isn't cloned locally — including every CI
  clean runner, so no `ci.yml` change is needed. Opt-out escape hatch `CURATED_SKILL_CARDS`
  (empty today) for a card that documents its own decision to curate a skill subset instead of
  full-mirroring.
- **`scripts/git-hooks/pre-push`** — opt-in local hook re-running the drift gate on every omha
  push (`git config core.hooksPath scripts/git-hooks` once to enable). Not wired into CI.

### Cards
- `omd.json` `triggers.skills` was missing `docs-pdf` (live drift against
  `oh-my-docs` 0.5.4's `plugin.json`, caught by the new test on day one).

## 0.8.0 — 2026-07-19
A hard-gate release: routing goes from advisory (text-channel instruction the
model could carry forward by inertia) to enforced (hook-level block/deny at
the moment a real-work tool actually fires). Rolls up ~29 commits since 0.7.2.

### Added
- **Hard-gate enforcement via `hooks/route_guard.py` (PreToolUse) and
  `hooks/route_stop_guard.py` (Stop).** `route_guard.py` denies
  `Bash|Agent|Task|Edit|Write` tool calls whenever the current turn has not
  declared a fresh `ROUTE →` line, forcing re-judgment instead of letting a
  stale prior-turn verdict carry forward by inertia (the compliance-gap
  failure mode a text-only instruction cannot enforce). `route_stop_guard.py`
  is the backstop for turns that call no tool at all (pure chat), blocking
  `Stop` until a ROUTE line is emitted. Both fire once per turn via a shared
  session-keyed sentinel (never nag a multi-tool turn twice) and are
  flush-race tolerant (bounded 3-attempt re-scan, ≤0.30s, for the case where a
  tool fires before the assistant's ROUTE text is flushed to the transcript).

### Changed
- **ROUTE line now emitted only on lane switch**, not unconditionally every
  turn — cuts output noise on same-lane continuation turns while the
  re-judgment *obligation* (and the hard gate enforcing it) still applies
  every turn regardless of output.
- **Re-routing/re-judgment hardening in `route_emit.py`**: ROUTE forced every
  turn irrespective of action count (closes a 1–2 action omission loophole);
  a sub-task delegation moment re-triggers routing judgment; OMC set as the
  default work-style lane with superpowers narrowed to an explicit-request
  gate (was over-catching general coding/planning via broad phrasing);
  external repo/plugin investigation routes to OMC regardless of action count;
  docker/env asset work (Dockerfile/compose) routes to omp, not handle-directly.
- **`handle-directly` code-fact assertion gate** narrowed to trigger at
  assertion-time (the point the model can actually self-notice) rather than
  by task category, with the verification procedure deferred to
  `.claude/rules/03` instead of duplicated in the router.

### Fixed
- Transcript flush-race false-denies in `route_guard.py` and false-blocks in
  `route_stop_guard.py`: a real-work tool or Stop event could fire before the
  assistant's ROUTE text was flushed to the JSONL, causing a legitimate ROUTE
  turn to be scanned as empty. Both hooks now bounded-retry (3 attempts,
  0.15s apart) before concluding a turn truly has no ROUTE line.

### Cards
- `omp.json` synced through the secretary axis (0.4.0 log/brief/review,
  0.5.0 handoff stage); `oms.json` synced through 0.8.0 (packaging),
  0.9.0 (knowledge-lifecycle), and 0.11.0 (scholar-read/scholar-discuss).
- Routine version-drift syncs bringing `omx`/`oms`/`omd`/`omp` cards current
  with their sibling plugin releases (2026-07-16 patch round and after).

## 0.7.2 — 2026-06-17
### Changed
- **ANALYZE/ROUTE now render as a GFM blockquote.** The injected checkpoint
  previously told the model to emit `ANALYZE →` as a plain line with `·`
  middle-dot fields, which markdown does not parse as a list — the labels
  collapsed into one indented blob and the block did not visually separate from
  the answer body. The format instruction now asks for a `> **ANALYZE**` header
  with `> - **label**:` bullets, and ROUTE on a `> **ROUTE →**` quoted line tied
  into the same quote box via a blank `>` line, so ANALYZE+ROUTE read as one
  bordered block distinct from the prose. No emoji (terminal Korean-width safe).
  The `ROUTE →` substring is preserved inside the bold so the ordering test
  (`ctx.index("ANALYZE") < ctx.index("ROUTE →")`) still holds — no test changes.

## 0.7.1 — 2026-06-17
### Fixed
- **ANALYZE/ROUTE output order made unambiguous.** The 0.7.0 instruction said
  "emit ANALYZE before ROUTE" but every other routing block (`<oms-routing>`,
  `<omd-routing>`, the omha body) says "emit ROUTE at the very front", and the
  model resolved the conflict by putting ROUTE first and ANALYZE below it. The
  closing instruction now explicitly states **ANALYZE sits above ROUTE** and that
  this order overrides the "ROUTE at the front" wording when the gate applies.
  Removed the ambiguous "맨 앞에 이 한 줄로" phrasing that fed the conflict.
  Added a test asserting the explicit ordering clause is present.

## 0.7.0 — 2026-06-17
An analyze-before-route release: the routing hook now asks for a one-shot
requirements analysis *before* the ROUTE line, so the lane verdict and the work
that follows are grounded in a decomposed reading of the request instead of a
raw guess.

### Added
- **`ANALYZE → … then ROUTE` in `route_emit.py`.** The injected checkpoint now
  instructs a requirements decomposition (목적 / 핵심 요구 / 제약 / 모호한 점)
  to be emitted *before* the ROUTE line. Routing and execution are based on that
  analysis — the goal is to finish in one pass instead of misreading the request
  and burning tokens on a rollback.
  - **Gated to 3+ actions / multi-file / ambiguous requests only.** Simple,
    unambiguous 1–2 action requests skip ANALYZE and emit ROUTE directly — the
    analysis itself costs output tokens, so forcing it on trivial asks would
    invert the token-saving intent. Same gate omha already uses for the ROUTE
    verdict.
  - **Ambiguity halts before work.** If the `모호한 점` field is anything other
    than "없음", the model must confirm with the user *before* proceeding to
    ROUTE/execution — this is the actual lever that prevents misunderstand-then-redo.

## 0.6.0 — 2026-06-05
A routing-model release: the cascade grows from "work-style lanes only" into a
three-axis model — **governance (omp) → content domains (oms/omd) → work-style
(omc/sp/omx)** — and three sibling harnesses (omx, oms, omd, omp) become
first-class routing cards instead of demoted 2nd-tier installed skills.

### Added
- **Governance axis — `cards/omp.json` (lane_type `governance`), judged FIRST.**
  oh-my-project (project-folder structure / placement / `.omp` rules) was absent
  from the omha cascade entirely: the ROUTE enum is generated from `cards/*.json`
  names, so with no card, structure/placement work had no lane and fell through to
  handle-directly. Governance is an axis *orthogonal* to the content domains — the
  same `.pptx` is omd when you author its content but omp when you ask whether it
  sits in the right folder — so a two-box (domain vs work-style) split could not
  place it. The card draws the omd/oms boundary explicitly (content authoring =
  oms/omd, folder placement/rules = omp) and names the `.omp/` index-coherence and
  safe-fileops guards that live only inside omp.
- **`oh-my-experiments` (omx) as a 3rd work-style lane** — `cards/omx.json`,
  glob-discovered by `route_emit.py` and `registry.py`, added to the ROUTE verdict
  enum. Distribution stays in OMX's own `omx` marketplace (no dual-publish here).
- **Domain-first routing cards — `cards/oms.json`, `cards/omd.json` (lane_type
  `domain`).** Paper (.tex/.bib → oms) and document (.pptx/.docx/.xlsx/.hwpx → omd)
  work is now enforced at the 1st tier instead of being a 2nd-tier installed-skill
  fallthrough — so "paper work must always enter oms" (where the citation guard
  lives) holds at the routing layer.
- **Marketplace registrations**: `oh-my-project` and `oh-my-experiments` added as
  github-source plugins alongside oh-my-docs / oh-my-scholar, so all siblings
  install the same way.
- **Re-routing clause: push heavy research to OMC** — the hook now advises that
  heavy literature / external-repo / library research be delegated to OMC research
  skills (`external-context` for outward web/docs/GitHub, `sciomc` for deep target
  analysis) rather than a single ad-hoc search. Injects a routing *rule*, not card
  knowledge (no-drift principle holds); preserves the "no OMC parallel for
  citation-bound paper research" guard.

### Changed
- **`hooks/route_emit.py`: 3-way `lane_type` split** (governance / domain /
  work-style). Cards are sorted into three boxes; the cascade is rewritten
  governance-first → domain → work-style. Unknown `lane_type` still falls to
  work-style, so the existing cards stay valid (backward compatible).
- **`cards/{omc,superpowers,omx}.json` → `lane_type: work-style`;
  `cards/{oms,omd}.json` → `domain`; `cards/omp.json` → `governance`.**
- **`registry.py`: `AgentCard` reads `lane_type`** (default `work-style` for
  backward compat).
- **`cards/omx.json` description = commitment to act, not a label** — declaring
  `ROUTE → oh-my-experiments` now obliges actually invoking an omx skill / the
  `.omx` engine, symmetric with how omc/sp enforce route→invoke (closes the
  hand-reading-TensorBoard anti-pattern, caught twice 2026-06-05).
- **README "Routing model"** rewritten from the old 3-tier (SP/OMC → installed
  domain skills → direct) to the governance→domain→work-style cascade with all
  current lanes named.

### Verification
- `route_emit.py` emits a valid `UserPromptSubmit` envelope; the ROUTE enum now
  includes `oh-my-project`, and the governance box renders above the domain box
  (checked by running the hook on `{}` stdin).
- Domain-first routing tests: `tests/test_domain_first_routing.py` (7) — domain
  cards present, lane_type assignment, extension triggers, domain-first context.
- 54 green at the domain-first cascade commit (`5793265`).

### Notes
- omp was already published (`luckkim123/oh-my-project`) and routed via its own
  `UserPromptSubmit` STAGE hook before this release; what 0.6.0 adds is its
  *omha-level* lane card, so the meta-router stops dropping governance work to
  handle-directly.
- The cache copy is pinned to a `gitCommitSha` in `installed_plugins.json`;
  picking up these cards on a machine requires a plugin update/reinstall (the
  marketplace `git pull` alone updates the marketplace mirror, not the live cache).

## 0.5.0 — 2026-05-29
### Added
- **Push channel: `PreToolUse` hook for cross-lane signal detection.** A new `hooks/cross_lane_emit.py` runs on every `Write` / `Edit` / `Skill` tool call, reads `cards/*.json` `triggers` blocks, and emits a hard-toned advisory envelope when the tool target maps to a lane different from what's currently in flight. Tool calls are never blocked — the model sees the advisory in `hookSpecificOutput.additionalContext` and is asked to prepend a STAGE re-route line. Directly addresses the v0.4.0 pull-side gap: even with "re-routing obligation" written into `<omha-routing>`, the model can miss mid-task transitions when context grows long. The push channel turns that from a self-discipline rule into an objective hook firing.
- **`triggers` block on AgentCard.** Cards may now declare `triggers.extensions[]` and `triggers.skills[]` — the push hook's opt-in registry. Backwards-compatible: cards without `triggers` route via pull only (push stays silent). SP/OMC cards now declare their characteristic skill names (writing-plans, test-driven-development, ultrawork, ralph, …). Extensions list is empty on work-style lanes by design — file extensions belong to domain cards (OMD/OMS/…).
- **Stateless 30-second same-lane cooldown** via `/tmp/omha_last_push.json`. Five consecutive `.pptx` writes inside an OMD task emit once, not five times (no token-flood). A lane switch mid-stream re-emits immediately — the transition is the strong signal worth surfacing. Fail-open on corrupt JSON.
- Tests: 30 new across hook + integration (signal extraction, lane matching, cooldown, fail-open, 4 plan §7.2 scenarios A/B/C/D, real SP/OMC card e2e through the hook). 11→47 green.

### Changed
- `src/omha/registry.py`: `AgentCard` gains an optional `triggers: AgentTriggers` field (also dev/CI-time only; the runtime hooks read cards with stdlib `json.loads`).
- `.claude-plugin/plugin.json`: `hooks.PreToolUse` registered alongside the existing `UserPromptSubmit`. Matcher `Write|Edit|Skill` only — `Read` floods (routine scans), `Bash` would need command parsing.

### Verification
- pytest: 47 green on Python 3.9 (was 11; +36 across schema, hook unit, plugin manifest, integration scenarios).
- Hook is stdlib-only — `test_hook_has_no_third_party_imports` enforces it.
- Fail-open paths covered: missing cards dir, corrupt cooldown JSON, garbage stdin, missing `tool_input` keys → exit 0 silent (never blocks a tool call).
- Live `claude -p` validation deferred to the install/marketplace cycle (separate session); the integration tests fully cover the four user-facing scenarios with fixture cards, so the mechanism is proven before deploy.

### Notes
- **Push is opt-in per card.** A card without `triggers` (legacy or by choice) gets pull routing only. Local skills not declared in any card stay in pull's domain — the model still sees them via the skill's own SKILL.md.
- SP/OMC cards declare push `skills` but no `extensions` — extensions are a *domain* concept (which file format) and SP/OMC are *work-style* lanes. Real domain push (OMD `.pptx`, OMS `.tex`, …) requires those plugins to ship cards with `triggers.extensions`; that's a separate, plugin-side change.
- Python 3.10 union syntax (`X | None`) avoided; `Optional[X]` used throughout for 3.9 compatibility (the registry promise).
- Design: `2026-05-29-omha-self-rerouting-design.md` (decisions + dialogue trail). Execution plan: `2026-05-29-omha-self-rerouting-execution.md`.

## 0.4.1 — 2026-05-28
### Changed
- **a2a-sdk dependency removed — omha is now fully dependency-free.** `0.3.0` declared "zero runtime deps — no a2a-sdk", but `src/omha/registry.py` still did `from a2a.types import AgentCard`, so on a Python 3.9 box (a2a-sdk requires ≥3.10) test collection failed. `registry.py` now validates cards with stdlib `dataclasses` (same `.name`/`.skills[].tags|examples` API the tests use), so the declared intent is realized in code. `pyproject.toml`: `dependencies = []`, `requires-python = ">=3.9"`.
- **`ROUTE →` one-liner: emoji removed.** The injected routing line is now plain text `ROUTE → …` (was `🧭 ROUTE → …`), matching the new omd `STAGE(docs) →` / oms `STAGE(paper) →` lines — text labels distinguish the layers, no emoji. (User request: no emoji.)
### Verification
- pytest: 11 green on Python 3.9 (was 2 collection errors from the missing a2a import). registry imports with no third-party deps.
### Notes
- Runtime path was always a2a-free (the hook reads cards with `json.loads`); this change removes the dev/CI-time a2a dependency too, so the whole repo runs anywhere Python 3.9+ is present.

## 0.4.0 — 2026-05-28
### Added
- **Cross-lane re-routing obligation**: the `<omha-routing>` hook context now states that even while working inside a tier-2 domain skill (OMD, slides, …), a heavy subtask that belongs to a work-style lane (parallel multi-source research, deep investigation, test-first code) must trigger a fresh lane judgment on the spot — not be handled inline. Includes a trivial guard (3-4 line fact checks stay direct, no over-attraction) and a citation guard (paper research is done but never with OMC parallelism). Directly fixes the reported symptom: "while OMD is loaded, work that needs OMC for research was just handled inline instead of routing to OMC."
- **Full 3-tier cascade in the hook text**: the injected context now spells out all three tiers (1: SP/OMC lanes → 2: installed domain skills → 3: handle-directly). Previously the hook only named tier-1 and tier-3, so the tier-2 domain layer that the v0.2.0 redesign defined was missing from what the session actually saw.
- `domain-skill` added as a fourth choice in the `🧭 ROUTE →` one-liner (was `oh-my-claudecode|superpowers|handle-directly`), so the session can declare "handling in a domain skill" — the prerequisite for then re-routing out of it.
- Tests: `test_context_states_three_tier_cascade`, `test_context_states_reroute_obligation` (TDD — written failing first, then the hook text was extended to pass).
### Changed
- `hooks/route_emit.py` `build_routing_context()` text only (cards untouched). Knowledge stays in `cards/*.json` (SSOT); the new text is cascade *procedure*, not lane identity, so no card duplication / drift.
### Verification
- pytest: 11 tests green (was 9; +2 new route_emit tests).
- Clean `claude -p` routing (legacy claude-settings routing already removed from live settings; omha is the sole router), loaded via `--plugin-dir` against the uncommitted source:
  - **cross-lane** "parallel research during slide work" → `ROUTE → oh-my-claudecode` (and the session applied the citation guard itself). The core target case.
  - **trivial** "one-line fact insert during slide work" → `ROUTE → handle-directly` (no over-attraction).
  - **regression** "rename across 20 files" → `ROUTE → oh-my-claudecode · ultrawork`; "root-cause-first bug" → recognized systematic-debugging (SP). No entry-routing regression.
- Cards were **not** tuned: the hook change alone resolved cross-lane, so card `examples` were left untouched to avoid the over-attraction regression (9/12) the v0.2.0 redesign measured.
### Notes
- This is the narrow *reverse* slice of the deferred stage-3 cross-lane distribution (domain → work-style re-routing), not the full split/order/merge/failure orchestration — that stays deferred (YAGNI). Design: `2026-05-28-omha-cross-lane-routing-design.md`.
- OMD's own `<Self_Sufficiency>` wording (`~/oh-my-docs/.../docs-pilot/SKILL.md`) was left unchanged: the omha-side fix resolves the symptom from above, per the design's "verify omha alone first" path. Revisit only if measurement later shows the OMD wording suppresses re-routing.

## 0.3.0 — 2026-05-28
### Added
- **stage-1 lane routing**: `hooks/route_emit.py` — a `UserPromptSubmit` hook that reads `cards/*.json` (stdlib `json` only, **zero runtime deps — no a2a-sdk**) and injects an `<omha-routing>` checkpoint every turn. The Claude Code session (LLM) does the lane judgment; the hook only feeds it the cards.
- `.claude-plugin/plugin.json` — omha is now a Claude Code **plugin** (registers the hook), while still being the heroacademia **marketplace**. Both manifests coexist in `.claude-plugin/`. `version` omitted (commit-SHA versioning).
- Tests: `test_route_emit.py` (context lists each lane + handle-directly; asserts no a2a import), `test_plugin_manifest.py` (hook registration + marketplace/plugin coexistence).
### Changed
- omha is now marketplace + plugin (was marketplace-only). `registry.py` (a2a validation) is now explicitly **dev/CI-time only** — the runtime hook never imports it.
### Verification
- pytest: 9 tests green (smoke, registry, cards_valid, route_emit, plugin_manifest).
- hook CLI: emits valid `UserPromptSubmit` envelope with both lanes.
- a2a isolation: hook runs with `a2a` blocked (runtime dep = 0).
- **Clean live-load routing** (claude-settings routing hooks temporarily OFF so only omha's hook was active, then restored): 4/4 correct on `claude -p` clean sessions — OMC (bulk edit), SP (root-cause-first), handle-directly (typo), domain-skill fallthrough (PPT → ppt-academic, not a lane). Confirms the 3-tier cascade and lane-not-skill granularity work in a real session.
### Notes
- The routing brain is the Claude Code session, not the hook. Cards = single source of truth; the hook reads, never embeds (no drift — the legacy claude-settings SKILL.md↔reminder.py duplication is not reproduced).
- omha's hook and claude-settings' `routing-verdict-reminder.py` both fire during the stage-1 coexistence period. Disabling the legacy claude-settings routing (Strangler Fig step 1 completion) is a separate, user-confirmed claude-settings change.

## 0.2.0 — 2026-05-28
### Removed
- HTTP server (`server.py`) + FastAPI/uvicorn deps + `omha` console entry point.
- Keyword router (`router.py`, `_score`) — routing brain moves to the Claude Code session (LLM), cards are the data it reads.
- `cards/omd.json` — OMD is a document *domain* tool, not a work-*style* harness; it ships via the heroacademia marketplace and is reached as an installed skill, not an omha routing card.
- `tests/test_server.py`, `tests/test_router.py`.
### Changed
- omha is now a declarative harness card registry, not a server. `registry.py` + `cards/*.json` (SP/OMC) remain; `a2a-sdk` kept (cards validated as A2A AgentCard), FastAPI/uvicorn/httpx dropped.
- Routing model = 3-tier fallback cascade (1: SP/OMC harness cards, 2: installed domain skills incl. OMD/ppt-academic/gen-image, 3: Claude Code direct). See `2026-05-28-omha-redesign-cards-not-server.md`.
- Cards are **harness-unit, not skill-unit**: each card describes the harness's lane identity + domain boundary + representative signals, not a full skill catalog (that stays in claude-settings `using-omc`, to avoid DRY violation and signal over-attraction). Verified on clean `claude -p` sessions: lean harness-unit cards routed 11/12 vs 9/12 for skill-unit cards (the one miss was LLM non-determinism, not a card defect).
### Verification
- pytest: smoke + registry + cards_valid — 5 tests, all green.
### Notes
- Rationale: the "server" was justified only by multi-machine federation, which turned out not to be a real requirement (machines sync via iCloud/git, not network calls). v0.1.0 server recoverable from git history (commit c01f95e) if federation is ever needed.

## 0.1.0 — 2026-05-27
### Added
- omha A2A HTTP server (stage-1 verdict-type router).
- Declarative card registry (`cards/*.json` -> A2A AgentCard) — new harness = drop a JSON file.
- 3 harness cards: superpowers + oh-my-claudecode (real), oh-my-docs (planned).
- Endpoints: `/harnesses`, `/harness/{name}/.well-known/agent-card.json`, `POST /route`.
- Console entry point: `omha`.
### Verification
- pytest: smoke + registry + cards + router + server — 14 tests, all green.
- Manual: `omha` boots on 127.0.0.1:8973, curl discovery + route verdict confirmed.
### Notes
- Forward/distribution (stage 2-3), auth, remote federation = NOT in this release (server-from-stage-1 by design).
- a2a-sdk pinned >=0.3,<0.4 (built against 0.3.26); re-verify before v1.0 (breaking migration exists).
- Stage-1 router is a deliberately coarse keyword judge; known limitations (punctuation tokenization, common-word example noise) deferred to stage 2.
