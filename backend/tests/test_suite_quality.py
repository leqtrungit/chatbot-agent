"""Test suite quality checks.

Enforces that all test functions contain actual assertions or statements
(not just `pass` or `...`). This prevents a recurrence of the M0-T7b bug
where 51 test functions were generated with empty bodies that always passed.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


def _walk_test_files() -> list[Path]:
    """Find all test_*.py files under backend/tests/."""
    tests_dir = Path(__file__).parent
    return sorted(tests_dir.glob("**/test_*.py"))


def _extract_test_functions(filepath: Path) -> dict[str, ast.FunctionDef]:
    """Extract all test_* functions from a Python file.

    Args:
        filepath: Path to a Python test file.

    Returns:
        Mapping of function name to AST node.
    """
    with open(filepath) as f:
        try:
            tree = ast.parse(f.read())
        except SyntaxError:
            # Skip files with syntax errors
            return {}

    functions = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            functions[node.name] = node
    return functions


def _get_function_body(func_node: ast.FunctionDef) -> list[ast.stmt]:
    """Extract the body of a function, skipping docstrings.

    Args:
        func_node: AST FunctionDef node.

    Returns:
        List of statements (excluding leading docstring).
    """
    body = func_node.body
    # Skip docstring if present
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return body


def _is_empty_test(func_node: ast.FunctionDef) -> bool:
    """Check if a test function is empty (only contains pass or ...).

    Args:
        func_node: AST FunctionDef node.

    Returns:
        True if the function body is empty or only contains pass/Ellipsis.
    """
    body = _get_function_body(func_node)

    # Empty body
    if not body:
        return True

    # Single pass statement
    if len(body) == 1 and isinstance(body[0], ast.Pass):
        return True

    # Single Ellipsis expression (...)
    if len(body) == 1 and isinstance(body[0], ast.Expr):
        expr = body[0].value
        if isinstance(expr, ast.Constant) and expr.value is ...:
            return True

    return False


def test_no_empty_test_functions() -> None:
    """Verify that no test function has an empty body.

    This guard prevents a recurrence of a batch code-generation bug (M0-T7b)
    where 51 test functions were created with empty bodies (just `pass`),
    making them always pass without actually testing anything.

    Raises:
        AssertionError: If any empty test functions are found.
    """
    violations: dict[Path, list[str]] = {}

    for filepath in _walk_test_files():
        functions = _extract_test_functions(filepath)
        empty_tests = []

        for func_name, func_node in functions.items():
            if _is_empty_test(func_node):
                empty_tests.append(func_name)

        if empty_tests:
            violations[filepath] = empty_tests

    if violations:
        message_lines = [
            "Found empty test functions (body is only `pass` or `...`).",
            "Each test must contain actual assertions or statements.",
            "",
        ]
        for filepath, empty_names in sorted(violations.items()):
            rel_path = filepath.relative_to(Path(__file__).parent.parent)
            for name in sorted(empty_names):
                message_lines.append(f"  {rel_path}::{name}")
        message_lines.append("")
        message_lines.append("Fix: Replace `pass`/`...` with real test logic (assert, etc.)")
        message_lines.append("Or delete the test entirely if it's not needed.")
        raise AssertionError("\n".join(message_lines))
