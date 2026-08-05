"""Smoke: adapters importable with Docker-matching PYTHONPATH (repo root + src)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_import_adapters_incognia_with_docker_pythonpath():
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{ROOT}:{ROOT / 'src'}"
    # cwd outside repo so import cannot rely on process cwd being on sys.path
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import adapters.incognia as m; assert hasattr(m, 'fetch_signals')",
        ],
        env=env,
        cwd="/tmp",
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
