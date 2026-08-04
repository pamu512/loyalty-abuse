import ast
from pathlib import Path


def test_core_does_not_import_fastapi():
    root = Path("src/loyalty_abuse")
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    assert not n.name.startswith("fastapi")
                    assert n.name != "uvicorn"
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("fastapi")
                assert node.module != "uvicorn"
