"""Re-entry lint: fails the build if a new root-literal string constant — for
EITHER store, the legacy `.omha` or the unified `.hq` — lands anywhere outside
hooks/omha_paths.py (the single declaration point, spec
~/oh-my-orchestrator/skills/harness/references/store-spec.md §9.5).

P4 widened this from one literal to two, mirroring oh-my-project's P3
widening of its own paths-module lint (tests/test_omp_paths_lint.py).
Guarding only the legacy root would leave the new root free to spread
through the hooks during the very refactor that exists to prevent exactly
that — the cutover is when a root string is most likely to be re-typed, not
least.

Violation rule (ast-based, not regex-on-text): a `str` ast.Constant —
including one nested inside an f-string's JoinedStr, since ast.walk descends
into those too — counts as a violation iff it CONTAINS a root literal AND
contains NO whitespace character at all. Paths never have spaces; prose
always does, so this is what tells a literal path (`".omha/routing.jsonl"`)
apart from a sentence that merely mentions one. A module, function,
async-function, or class docstring (the first statement, when it is a plain
`Expr(Constant(str))`) is explicitly exempt — that is where the prose
describing this whole convention necessarily lives.

Scope: every tracked `.py` file in the repo, minus:
  - `tests/**` — fixtures legitimately need the literal to build `.omha/`/
    `.hq/` paths on disk under tmp_path.
  - `hooks/omha_paths.py` — the one file allowed to declare the literal.

omha has neither a `references/` directory (data files copied into user
projects, per the shared P2 contract) nor `.phase0-scratch/` (omo-only) —
both spec exclusions are inapplicable here, same as before P4.
"""
import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
import omha_paths as op  # noqa: E402

ROOTS = (op.LEGACY_ROOT, op.HQ_ROOT)

REPO_ROOT = Path(__file__).resolve().parent.parent
PATHS_MODULE = REPO_ROOT / "hooks" / "omha_paths.py"
EXCLUDED_DIRS = {"tests"}


def _is_violation(value: str) -> bool:
    return any(r in value for r in ROOTS) and not any(ch.isspace() for ch in value)


def _docstring_constant_ids(tree: ast.AST) -> set:
    """id() of every Constant node that is a module/function/class docstring —
    the first statement of the node, when it is a plain `Expr(Constant(str))`."""
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                ids.add(id(body[0].value))
    return ids


def violations_in_source(source: str, filename: str = "<string>") -> list:
    """[(lineno, value), ...] — every non-docstring str Constant (f-string
    pieces included, via ast.walk descending into JoinedStr) that is a
    violation per `_is_violation`."""
    tree = ast.parse(source, filename=filename)
    skip = _docstring_constant_ids(tree)
    out = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in skip and _is_violation(node.value)):
            out.append((node.lineno, node.value))
    return out


def _scanned_files():
    for path in sorted(REPO_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts or ".venv" in path.parts or ".git" in path.parts:
            continue
        rel_parts = path.relative_to(REPO_ROOT).parts
        if rel_parts[0] in EXCLUDED_DIRS:
            continue
        if path == PATHS_MODULE:
            continue
        yield path


def test_scan_targets_exist():
    # a vacuous pass (0 files scanned) must not read as "0 violations, all clear"
    assert list(_scanned_files()), "no .py files found to scan — lint scope is broken"


def test_no_root_literal_reentry():
    offenders = []
    for path in _scanned_files():
        rel = path.relative_to(REPO_ROOT)
        for lineno, value in violations_in_source(path.read_text(encoding="utf-8"), str(rel)):
            offenders.append(f"{rel}:{lineno}: {value!r}")
    assert not offenders, (
        f"new {' or '.join(repr(r) for r in ROOTS)} literal(s) outside "
        "hooks/omha_paths.py — add a named helper there instead:\n" + "\n".join(offenders)
    )


# --- meta-tests: prove the detector itself actually bites -------------------

def test_meta_bare_literal_bites():
    assert violations_in_source('X = ".omha"\n') == [(1, ".omha")]


def test_meta_path_literal_bites():
    v = violations_in_source('X = ".omha/routing.jsonl"\n')
    assert len(v) == 1 and v[0][1] == ".omha/routing.jsonl"


def test_meta_fstring_piece_bites():
    v = violations_in_source('name = "x"\nX = f".omha/{name}.jsonl"\n')
    assert any(".omha/" in val for _, val in v)


def test_meta_prose_with_whitespace_is_not_a_violation():
    v = violations_in_source('X = ".omha/routing.jsonl 은 판정 로그다"\n')
    assert v == []


def test_meta_module_docstring_is_exempt():
    v = violations_in_source('""".omha/routing.jsonl is the log."""\nX = 1\n')
    assert v == []


def test_meta_function_docstring_is_exempt():
    v = violations_in_source(
        'def f():\n    """.omha/redact-patterns.txt holds patterns."""\n    return 1\n')
    assert v == []


def test_meta_hq_literal_bites():
    v = violations_in_source('X = ".hq/runtime/routing/routing.jsonl"\n')
    assert len(v) == 1 and v[0][1] == ".hq/runtime/routing/routing.jsonl"


def test_meta_hq_prose_with_whitespace_is_not_a_violation():
    v = violations_in_source('X = "이 앵커는 .hq 루트를 가리킨다"\n')
    assert v == []


def test_meta_non_docstring_string_still_bites():
    # a bare string statement that is NOT the first statement must not be
    # mistaken for a docstring
    v = violations_in_source('def f():\n    x = 1\n    ".omha/state"\n    return x\n')
    assert v == [(3, ".omha/state")]
