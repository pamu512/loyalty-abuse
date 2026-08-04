from notebooks.offline_eval import summarize_decisions


def test_summarize_decisions_counts():
    rows = [
        {"score": 10, "friction": "allow", "reasons": [], "typology_breakdown": []},
        {
            "score": 90,
            "friction": "block",
            "reasons": ["bot.redeem_velocity"],
            "typology_breakdown": [{"id": "bot_redeem"}],
        },
    ]
    s = summarize_decisions(rows)
    assert s["decision_count"] == 2
    assert s["friction_counts"]["block"] == 1
