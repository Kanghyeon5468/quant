"""Synthetic fixtures exercise the new research units without provider calls."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from quantcore.data.providers.coinbase_public import candles
from quantcore.data.providers.research_files import catalog, import_csv, series
from quantcore.factors.validation import neutral_scores, price_factor_validation
from quantcore.fundamentals.advanced import advanced_ratios
from quantcore.incremental.moments import RollingCovariance
from quantcore.machine_learning.research import extended_validation
from quantcore.macro.public import collect, report, usd_to_krw
from quantcore.statistics.timeseries import diagnostics
from quantcore.valuation.dcf import DCFAssumptions, dcf
from quantcore.valuation.research import ScenarioRequest, scenarios


def test_valuation_inverts_known_dcf_and_financial_amounts_keep_meaning():
    input_case = DCFAssumptions(growth=.11)
    result = scenarios(ScenarioRequest(
        dcf_assumptions=input_case, reverse_dcf_price=dcf(input_case)["per_share"], bull_growth=.20,
        dividend={"cash_flow": 2, "discount": .1, "growth": .05},
        segments=[{"name": "A", "enterprise_value": 30}, {"name": "B", "enterprise_value": 90}],
        segment_net_debt=20,
    ))["models"]
    assert result["reverse_dcf"]["implied_revenue_growth"] == pytest.approx(.11)
    assert result["bull_case"]["per_share"] > result["fcff"]["per_share"]
    assert result["dividend_discount"]["value"] == pytest.approx(42)
    assert result["sum_of_parts"]["equity_value"] == 100


def test_advanced_financial_indicators_keep_unobserved_components_unavailable():
    current = {"revenue": 365, "cost_of_revenue": 365, "inventory": 20, "receivables": 10,
               "payables": 5, "net_income": 2, "assets": 25, "operating_cash_flow": 4}
    rows, piotroski = advanced_ratios(current, current)
    values = {row["name"]: row["value"] for row in rows}
    assert values["cash_conversion_cycle"] == pytest.approx(25)
    assert all(values[name] is None for name in ("altman_z", "piotroski_f_proxy", "beneish_m_proxy"))
    assert piotroski["profitable"] is True and piotroski["no_cash_common_stock_issuance"] is None


def test_public_macro_keeps_source_times_and_handles_calendar_denial(tmp_path):
    today = datetime.now(timezone.utc).date().isoformat()

    def origin(request):
        if request.url.host == "www.bls.gov":
            return httpx.Response(403)
        if request.url.host == "www.federalreserve.gov":
            html = f'<h4>{today[:4]} FOMC Meetings</h4><div class="fomc-meeting__month"><strong>December</strong></div>'
            html += '<div class="fomc-meeting__date">8-9*</div>'
            return httpx.Response(200, text=html)
        key = request.url.params["id"]
        value = {"DGS10": 5, "DGS2": 4, "DEXKOUS": 1200}.get(key, 1)
        return httpx.Response(200, text=f"observation_date,{key}\n{today},{value}\n")

    collect(tmp_path, httpx.MockTransport(origin))
    snapshot = report(tmp_path)
    assert snapshot["status"] == "partial" and snapshot["failures"] == {"bls_calendar": 403}
    assert snapshot["calendar"]["fomc"]["events"][0]["scheduled_date"] == today[:4] + "-12-09"
    assert snapshot["curve"] == [{"period": today, "spread_pp": "1"}]
    assert usd_to_krw(snapshot, Decimal("2"))["krw"] == "2400"


def test_incremental_covariance_matches_batch_and_rebuilds_revised_overlap():
    frame = pd.DataFrame(np.random.default_rng(42).normal(size=(30, 3)))
    compute = RollingCovariance()
    assert np.allclose(compute.update(frame.iloc[:26], "a"), frame.iloc[:26].cov())
    assert np.allclose(compute.update(frame.iloc[4:], "b"), frame.iloc[4:].cov())
    assert compute.report() == {"rebuilds": 1, "appended": 4, "evicted": 4, "cache_hits": 0}
    revised = frame.iloc[4:].copy()
    revised.iloc[0, 0] *= 4
    assert np.allclose(compute.update(revised, "c"), revised.cov())
    assert compute.report()["rebuilds"] == 2


def test_factor_periods_and_model_purge():
    index = pd.date_range("2025-01-01", periods=260, tz="UTC")
    random = np.random.default_rng(10).normal(0, .01, (260, 4))
    close = pd.DataFrame(100*np.exp(random.cumsum(axis=0)), index=index, columns=list("ABCD"))
    result = extended_validation(close["A"])
    assert all(row["train_last_target"] < row["test_start"] for row in result["folds"])
    assert any(row["model"] == "random_forest" for row in result["models"])
    assert any(row.get("mean_abs_linear_shap") for row in result["models"])
    frames = {name: pd.DataFrame({"open": close[name], "close": close[name]}) for name in close}
    factor = price_factor_validation(frames)
    assert [row["holding_sessions"] for row in factor["horizons"]] == [1, 5, 20]
    neutral = neutral_scores(
        [{"symbol": name, "market_cap_estimate": i+1, "score": (-1)**i} for i, name in enumerate(close)], {},
    )
    assert sum(row["neutral_score"] for row in neutral["rows"]) == pytest.approx(0)
    study = diagnostics(close, "A", "B")
    assert study["tests"]["cointegration"]["status"] == "ok"
    assert len(study["granger_predictability"]) == 2


def test_market_bars_keep_precision_and_require_source_metadata(tmp_path):
    observed = datetime.now(timezone.utc)
    yesterday = observed - timedelta(days=2)
    sample = candles([[yesterday.timestamp(), 99, 110, 100, 105, .0042]], observed.isoformat())
    assert sample[0]["volume"] == "0.0042"
    path = tmp_path/"fixture.csv"
    path.write_text("timestamp,available_at,open,high,low,close,volume\n"+
                    f"{yesterday.isoformat()},{observed.isoformat()},100,110,99,105,420\n")
    instrument = {"symbol": "SAMPLE", "name": "controlled fixture", "asset_class": "equity", "currency": "KRW",
                  "exchange_timezone": "Asia/Seoul", "source": "synthetic test", "volume_unit": "shares",
                  "license_note": "test data"}
    import_csv(tmp_path, instrument, path)
    assert catalog(tmp_path) == ["SAMPLE"]
    assert series(tmp_path, "SAMPLE")["metadata"]["currency"] == "KRW"


def test_viewer_cannot_read_paper_or_post_research(tmp_path, monkeypatch):
    keys = {"view-test-key": "viewer", "research-test-key": "researcher"}
    stored = {hashlib.sha256(key.encode()).hexdigest(): role for key, role in keys.items()}
    monkeypatch.setenv("QUANTCORE_API_USERS_JSON", json.dumps(stored))
    with TestClient(create_app(directory=tmp_path, data_source="demo")) as client:
        viewer = {"Authorization": "Bearer view-test-key"}
        researcher = {"Authorization": "Bearer research-test-key"}
        assert client.get("/api/overview").status_code == 401
        assert client.get("/api/session-role", headers=viewer).json()["role"] == "viewer"
        assert client.get("/api/paper-performance", headers=viewer).status_code == 403
        assert client.post("/api/options", json={}, headers=viewer).status_code == 403
        assert client.post("/api/ws-ticket", headers=viewer).status_code == 200
        assert client.post("/api/options", json={}, headers=researcher).status_code == 200
        metrics = client.get("/api/metrics", headers=viewer)
        assert metrics.status_code == 200 and "quantcore_recent_latency_seconds" in metrics.text
