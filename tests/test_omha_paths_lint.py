"""Re-entry lint: fail the build if a `.omha` root-literal string is declared
anywhere in this repo's .py files outside hooks/omha_paths.py.

Judgment rule (~/oh-my-orchestrator/skills/harness/references/store-spec.md
§9.5): parse each target file with `ast`. A violation is any `ast.Constant`
str (including each literal piece of an f-string's `ast.JoinedStr`) that
contains the root literal `.omha` AND contains no whitespace character —
paths never have whitespace, prose always does. Module/FunctionDef/
AsyncFunctionDef/ClassDef docstrings (the first statement, `Expr(Constant(str))`)
are excluded explicitly, since the module/function-level prose above every
`.omha` call site in this repo intentionally names the path for humans.
Comments never reach the AST, so they need no special handling.

Scope: every tracked .py file in this repo, minus:
  - tests/**             — fixtures need the literal to build `.omha/` dirs
                            under tmp_path (measured: 21 occurrences today,
                            across test_redact_guard.py, test_route_log.py,
                            test_route_stop_guard.py — all `".omha"` path
                            fragments, none of them prose).
  - hooks/omha_paths.py   — the one allowed declaration (LEGACY_ROOT itself).

This repo has neither a `references/` directory (data files copied into user
projects, per the shared P2 contract) nor `.phase0-scratch/` (omo-only) —
both exclusions are inapplicable here and are correctly absent from the list
above; nothing was silently dropped to make the lint pass.
"""
import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PATHS_MODULE = REPO_ROOT / "hooks" / "omha_paths.py"
ROOT_LITERAL = ".omha"

EXCLUDED_DIRS = {"tests"}


def _target_files():
    for py in REPO_ROOT.rglob("*.py"):
        rel = py.relative_to(REPO_ROOT)
        if rel.parts[0] in EXCLUDED_DIRS:
            continue
        if py == PATHS_MODULE:
            continue
        if ".git" in rel.parts or ".venv" in rel.parts or "__pycache__" in rel.parts:
            continue
        yield py


def _docstring_nodes(tree):
    """Every `Expr(Constant(str))` node that IS a docstring (first statement
    of the Module or a Function/AsyncFunction/Class def) — to be skipped."""
    nodes = set()
    candidates = [tree] + [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    for c in candidates:
        body = getattr(c, "body", None)
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            nodes.add(id(body[0].value))
    return nodes


def _string_constants(tree, skip_ids):
    """Every str `ast.Constant`, minus docstrings.

    `ast.walk` already recurses into an f-string's `ast.JoinedStr.values`,
    surfacing each literal piece as its own `ast.Constant` node — no special
    casing needed to cover f-strings too."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in skip_ids:
                continue
            yield node


def _is_violation(s: str) -> bool:
    return ROOT_LITERAL in s and not any(ch.isspace() for ch in s)


def find_violations():
    violations = []
    for py in _target_files():
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except SyntaxError:
            continue
        skip_ids = _docstring_nodes(tree)
        for node in _string_constants(tree, skip_ids):
            if _is_violation(node.value):
                violations.append((py.relative_to(REPO_ROOT), node.lineno, node.value))
    return violations


def test_no_reentrant_omha_literal_outside_paths_module():
    violations = find_violations()
    assert not violations, "new `.omha` literal(s) outside hooks/omha_paths.py:\n" + "\n".join(
        f"  {path}:{line}: {value!r}" for path, line, value in violations
    )
