#!/usr/bin/env python3
"""CLI for the adversarial eval suite (primary B+ proof)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from loyalty_abuse.eval.adversarial import run_suite  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", type=Path, default=Path("artifacts/adversarial_v2_1.json"))
    args = p.parse_args()
    report = run_suite(seed=args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"gates_pass": report["gates_pass"], "gates": report["gates"]}, indent=2))
    print(f"wrote {args.out}")
    return 0 if report["gates_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
