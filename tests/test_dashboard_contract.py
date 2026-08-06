"""Dashboard contract — analytics summary exposes ops surfaces."""

from fastapi.testclient import TestClient

from loyalty_abuse_api.app import create_app


def test_analytics_has_dashboard_fields(tmp_path):
    client = TestClient(create_app(db_path=tmp_path / "dash.db"))
    # auth disabled in conftest
    r = client.get("/v1/analytics/summary")
    assert r.status_code == 200
    data = r.json()
    for key in (
        "friction_counts",
        "top_reasons",
        "typology_rates",
        "p_abuse_histogram",
        "insult_proxy",
    ):
        assert key in data
