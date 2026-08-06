from fastapi.testclient import TestClient
from loyalty_abuse_api.analytics import build_summary, _floor_raised
from loyalty_abuse_api.app import create_app
from tests.api_helpers import authed_client


def test_summary_empty(tmp_path):
    client = TestClient(create_app(db_path=tmp_path / "t.db"))
    r = client.get("/v1/analytics/summary")
    assert r.status_code == 200
    assert r.json()["decision_count"] == 0


def test_build_summary_aggregates():
    rows = [
        {
            "score": 10,
            "friction": "allow",
            "reasons": [],
            "typology_breakdown": [],
        },
        {
            "score": 90,
            "friction": "block",
            "reasons": ["bot.redeem_velocity", "promo.stack_depth"],
            "typology_breakdown": [
                {"id": "bot_redeem", "points": 30, "reasons": ["bot.redeem_velocity"]},
                {"id": "promo_stack", "points": 20, "reasons": ["promo.stack_depth"]},
            ],
        },
    ]
    s = build_summary(rows)
    assert s["decision_count"] == 2
    assert s["friction_counts"]["block"] == 1
    assert s["friction_counts"]["allow"] == 1
    assert s["score_histogram"]["10-19"] == 1
    assert s["score_histogram"]["90-99"] == 1
    assert s["top_reasons"][0]["reason"] == "bot.redeem_velocity"
    assert s["typology_rates"]["bot_redeem"] == 0.5


def test_floor_raised_soft_floor_reason():
    assert _floor_raised(
        {
            "friction": "soft_challenge",
            "score": 10,
            "reasons": ["floor.soft.slow_multi"],
            "features_snapshot": {"band_friction": "allow"},
        }
    )


def test_floor_raised_hard_floor_above_band():
    assert _floor_raised(
        {
            "friction": "hard_challenge",
            "score": 10,
            "reasons": [],
            "features_snapshot": {"band_friction": "allow", "force_hard_floor": True},
        }
    )


def test_floor_raised_false_when_band_matches():
    assert not _floor_raised(
        {
            "friction": "allow",
            "score": 10,
            "reasons": [],
            "features_snapshot": {"band_friction": "allow"},
        }
    )
