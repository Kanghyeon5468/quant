import numpy as np
import pandas as pd
import pytest

from quantcore.derivatives.options import black_scholes, implied_volatility
from quantcore.factors.engine import factor_scores, rank_ic
from quantcore.fundamentals.analysis import analyze
from quantcore.indicators.technical import technical
from quantcore.portfolio.optimization import optimize
from quantcore.risk.analytics import risk_report
from quantcore.valuation.dcf import DCFAssumptions, dcf, monte_carlo, sensitivity


def test_indicators_known_constant(flat_frame):
    t = technical(flat_frame)
    row = t.iloc[-1]
    assert row.sma_20 == row.ema_20 == row.wma_20 == 100
    assert row.rsi_14 == 50
    assert row.atr_14 == 2
    assert row.macd == row.macd_signal == row.macd_histogram == 0
    assert row.bollinger_upper == row.bollinger_lower == 100
    assert row.vwap_proxy_20 == 100
    assert row.stochastic_k == row.stochastic_d == 50
    assert row.obv == row.roc_20 == row.volatility_20 == 0
    assert row.donchian_upper == 101 and row.donchian_lower == 99
    assert row.keltner_upper == 104 and row.keltner_lower == 96
    assert row.ichimoku_span_a == row.ichimoku_span_b == 100


def test_known_increasing_indicators(flat_frame):
    f = flat_frame.copy()
    f['close'] = np.arange(1., 101.)
    f['open'] = f.close
    f['high'], f['low'], f['volume'] = f.close+1, f.close-1, 100
    row = technical(f).iloc[-1]
    assert row.sma_20 == 90.5
    assert row.wma_20 == pytest.approx(np.dot(np.arange(81, 101), np.arange(1, 21))/210)
    assert row.rsi_14 == row.adx_14 == 100
    assert row.obv == 9900
    assert row.roc_20 == 25
    assert row.vwap_proxy_20 == 90.5


def test_indicators_are_causal(frame):
    full = technical(frame)
    prefix = technical(frame.iloc[:400])
    pd.testing.assert_frame_equal(full.iloc[:400], prefix)
    with pytest.raises(ValueError):
        technical(frame.iloc[0:0])
    with pytest.raises(ValueError):
        technical(frame.iloc[::-1])


def test_financial_ratios_and_unavailable(service):
    result = service.fundamentals('QALPHA')
    values = {r['name']: r['value'] for r in result['metrics']}
    assert values['revenue_growth'] == pytest.approx(.08)
    assert values['gross_margin'] == .45
    assert values['current_ratio'] == 2
    assert values['interest_coverage'] == 21
    assert all(r['source'] and r['available_at'] and r['formula'] for r in result['metrics'])
    assert analyze([])['status'] == 'missing'
    facts = service.store.fundamentals('QALPHA', service.as_of)
    facts[-1] = {**facts[-1], 'industry': 'bank', 'interest_expense': 0}
    bank = {r['name']: r for r in analyze(facts)['metrics']}
    assert bank['debt_to_equity']['value'] is None
    assert bank['interest_coverage']['status'] == 'not_applicable'


def test_dcf_perpetuity_and_sensitivity():
    a = DCFAssumptions(revenue=100, growth=0, operating_margin=.2, tax_rate=0, depreciation_ratio=0,
        capex_ratio=0, working_capital_ratio=0, wacc=.1, terminal_growth=0, net_debt=0, shares=1)
    assert dcf(a)['per_share'] == pytest.approx(200., abs=1e-10)
    assert dcf(a.model_copy(update={'wacc': .12}))['per_share'] < 200
    assert len(sensitivity(a)) == 9
    assert monte_carlo(a, 100) == monte_carlo(a, 100)
    with pytest.raises(ValueError):
        DCFAssumptions(wacc=.02, terminal_growth=.03)


def test_black_scholes_reference_and_parity():
    call = black_scholes(100, 100, 1, .05, .2)
    put = black_scholes(100, 100, 1, .05, .2, 'put')
    assert call['price'] == pytest.approx(10.450583572185565, abs=1e-10)
    assert put['price'] == pytest.approx(5.573526022256971, abs=1e-10)
    assert call['price']-put['price'] == pytest.approx(100-100*np.exp(-.05))
    assert implied_volatility(call['price'], 100, 100, 1, .05) == pytest.approx(.2)
    with pytest.raises(ValueError):
        black_scholes(0, 100, 1, .05, .2)


@pytest.mark.parametrize('method', ['equal_weight', 'minimum_variance', 'risk_parity'])
def test_optimizer_constraints(service, method):
    result = optimize(service.returns(), method, .4)
    weights = np.array(list(result['weights'].values()))
    assert weights.sum() == pytest.approx(1., abs=1e-7)
    assert weights.min() >= -1e-8 and weights.max() <= .4+1e-8
    assert sum(result['risk_contribution'].values()) == pytest.approx(1.)


def test_infeasible_optimizer_and_risk(service):
    with pytest.raises(ValueError):
        optimize(service.returns(), max_weight=.1)
    with pytest.raises(ValueError):
        optimize(service.returns(), method='unsupported')
    with pytest.raises(ValueError):
        optimize(service.returns().iloc[:1])
    with pytest.raises(ValueError):
        risk_report(service.returns(), [1])
    with pytest.raises(ValueError):
        risk_report(service.returns(), [-1, 0, 0, 0, 0, 2])
    with pytest.raises(ValueError):
        risk_report(service.returns(), [1/6]*6, confidence=1)


def test_known_var_expected_shortfall():
    returns = pd.DataFrame({'a': [-.1, -.05, 0., .05, .1]})
    result = risk_report(returns, [1.])
    assert result['historical_var'] == pytest.approx(.09)
    assert result['expected_shortfall'] == .1
    assert result['stress_tests'][0]['kind'] == 'hypothetical'


def test_factors_pit_weights_neutralization(service):
    assert factor_scores(service.store, '2023-01-01T00:00:00Z') == []
    result = factor_scores(service.store, service.as_of)
    assert len(result) == 6
    assert sum(r['score'] for r in result) == pytest.approx(0, abs=1e-10)
    neutral = factor_scores(service.store, service.as_of, sector_neutral=True)
    assert len(neutral) == 6
    for weights in ({'unknown': 1}, {'momentum': -1}, {'momentum': 0}):
        with pytest.raises(ValueError):
            factor_scores(service.store, service.as_of, weights)
    s = pd.Series([1., 2., 3.])
    assert rank_ic(s, s) == 1
    assert rank_ic(s, -s) == -1
    assert rank_ic(s.iloc[:2], s.iloc[:2]) is None
