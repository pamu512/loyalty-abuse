import ast
from pathlib import Path


def _forbidden_module(name: str | None) -> bool:
    if not name:
        return False
    if name.startswith("fastapi") or name == "uvicorn":
        return True
    if name == "incognia" or name.startswith("incognia.") or name.startswith("adapters.incognia"):
        return True
    return False


def test_core_does_not_import_fastapi_or_incognia():
    root = Path("src/loyalty_abuse")
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    assert not _forbidden_module(n.name), f"{path}: import {n.name}"
            if isinstance(node, ast.ImportFrom):
                assert not _forbidden_module(node.module), f"{path}: from {node.module}"

