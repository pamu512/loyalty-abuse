"""Health / ready / metrics probes."""

from fastapi.testclient import TestClient

from loyalty_abuse_api.app import create_app


def test_healthz_readyz_metrics(tmp_path):
    client = TestClient(create_app(db_path=tmp_path / "h.db"))
    assert client.get("/healthz").status_code == 200
    assert client.get("/healthz").json()["status"] == "ok"
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"
    m = client.get("/metrics")
    assert m.status_code == 200
    assert "loyalty_abuse_requests_total" in m.text
    assert "text/plain" in m.headers["content-type"]
