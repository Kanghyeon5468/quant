"""Policy arithmetic and time/coverage boundaries; no operational substitute data."""

import copy

import pytest

from quantcore.strategies.information import DecisionPolicy, evaluate

CUT = "2026-11-25T12:00:00Z"


class Inputs:
    def __init__(self):
        self.financial = {"metrics": []}
        self.info = {
            "institutions": {"managers": []},
            "news": {"articles": []},
            "llm": {"analyses": []},
            "earnings_calls": {"documents": []},
        }

    def financials(self, symbol, cutoff):
        return self.financial

    def report(self, symbol, cutoff):
        return self.info


def test_missing_information_does_not_become_neutral_or_invented_sentiment():
    result = evaluate(Inputs(), "UNIT", CUT, DecisionPolicy(enabled=True))
    assert (
        result["status"] == "unavailable" and result["combined_score"] is None and result["multiplier"] == 1
    )
    assert all(v is None for v in result["scores"].values())


@pytest.mark.parametrize("value,expected", [(-1, 0.5), (0, 0.75), (1, 1)])
def test_signed_financial_score_controls_allocation_without_exceeding_base(value, expected):
    inputs = Inputs()
    inputs.financial = {
        "period_end": "2026-09-30",
        "metrics": [{"name": "revenue_growth", "value": value * 0.2}, {"name": "roe", "value": value * 0.25}],
        "source_url": "https://www.sec.gov/",
        "available_at": "2026-11-25T01:00:00Z",
    }
    result = evaluate(inputs, "UNIT", CUT, DecisionPolicy(enabled=True))
    assert result["multiplier"] == expected and result["scores"]["news"] is None


def test_stale_13f_and_old_articles_are_not_used_as_current_signals():
    inputs = Inputs()
    inputs.info["institutions"]["managers"] = [
        {"report_date": "2025-12-31", "prior_report_date": "2025-09-30", "holdings": []}
    ]
    inputs.info["news"]["articles"] = [{"created_at": "2026-11-01T00:00Z"}]
    result = evaluate(inputs, "UNIT", CUT, DecisionPolicy(enabled=True))
    assert result["scores"]["institutions"] is None and result["scores"]["news"] is None


def test_partial_or_previous_quarter_llm_cannot_stand_in_for_current_earnings():
    inputs = Inputs()
    inputs.info["earnings_calls"]["documents"] = [{"fiscal_year": 2026, "quarter": "Fourth Quarter"}]
    row = {
        "kind": "earnings_release",
        "sentiment": -1,
        "available_at": "2026-11-25T01:00:00Z",
        "document_key": "unit",
        "source_sha256": "unit",
        "model": "unit",
        "total_chunks": 2,
        "chunk": 0,
        "fiscal_year": 2026,
        "quarter": "Fourth Quarter",
    }
    inputs.info["llm"]["analyses"] = [row]
    assert evaluate(inputs, "UNIT", CUT, DecisionPolicy(enabled=True))["scores"]["earnings"] is None
    inputs.info["llm"]["analyses"].append({**row, "chunk": 1})
    assert evaluate(inputs, "UNIT", CUT, DecisionPolicy(enabled=True))["scores"]["earnings"] == -1
    inputs.info["llm"]["analyses"] = copy.deepcopy(inputs.info["llm"]["analyses"])
    for r in inputs.info["llm"]["analyses"]:
        r["quarter"] = "Third Quarter"
    assert evaluate(inputs, "UNIT", CUT, DecisionPolicy(enabled=True))["scores"]["earnings"] is None
