#!/usr/bin/env python3
"""Mock HTTP warehouse — complete gates; incomplete never eligible:true."""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_FIX = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(_REPO / "src"))

from loyalty_abuse.multi_gate import evaluate_loyalty_economics  # noqa: E402
from loyalty_abuse.warehouse import (  # noqa: E402
    fetch_loyalty_warehouse_pack,
    validate_loyalty_warehouse_pack,
)


class _Handler(BaseHTTPRequestHandler):
    routes: dict[str, Path] = {}

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        target = self.routes.get(path)
        if target is None or not target.is_file():
            self.send_response(404)
            self.end_headers()
            return
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    complete = _FIX / "loyalty_warehouse_complete.json"
    incomplete = _FIX / "loyalty_warehouse_incomplete.json"
    if not complete.is_file() or not incomplete.is_file():
        print("missing fixtures under scripts/fixtures/", file=sys.stderr)
        return 1
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    _Handler.routes = {
        "/complete": complete,
        "/incomplete": incomplete,
    }
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        ok = fetch_loyalty_warehouse_pack(f"{base}/complete")
        assert ok["gates_preview"]["order_decision_untouched"] is True
        try:
            validate_loyalty_warehouse_pack(json.loads(incomplete.read_text()))
            # incomplete may validate structure but gates must not be eligible:true
        except Exception:
            pass
        bad = json.loads(incomplete.read_text())
        from loyalty_abuse.multi_gate import evaluate_loyalty_economics as ev

        g = ev(
            entity_id=str(bad.get("entity_id") or "e1"),
            feed_snapshot=bad.get("loyalty_feed_snapshot"),
            program_config=bad.get("loyalty_program_config"),
        )
        for name, gate in (g.get("gates") or {}).items():
            assert gate.get("eligible") is not True, name
        print("loyalty_warehouse_smoke: OK")
        return 0
    finally:
        srv.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
