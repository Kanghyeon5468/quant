"""Statement-based ratios with explicit point-in-time and business applicability."""
from math import isfinite
from operator import eq, gt, lt


def _ratio(numerator, denominator):
    return numerator / denominator if numerator is not None and denominator is not None and denominator > 0 else None


def _sum(*values):
    return sum(values) if all(value is not None for value in values) else None


def _change(now, before):
    return _sum(now, -before if before is not None else None)


def advanced_ratios(current, prior, market_cap=None, *, manufacturer=False):
    now, old = current.get, prior.get
    assets, old_assets = now("assets"), old("assets")
    revenue, old_revenue = now("revenue"), old("revenue")
    cost = now("cost_of_revenue")

    def average(key):
        return _ratio(_sum(now(key), old(key)), 2)

    inventory = _ratio(average("inventory"), cost)
    receivables = _ratio(average("receivables"), revenue)
    payables = _ratio(average("payables"), cost)
    ccc = 365*(inventory+receivables-payables) if None not in (inventory, receivables, payables) else None
    working_capital = _change(now("current_assets"), now("current_liabilities"))
    z_inputs = [
        _ratio(working_capital, assets), _ratio(now("retained_earnings"), assets),
        _ratio(now("operating_income"), assets), _ratio(market_cap, now("liabilities")), _ratio(revenue, assets),
    ]
    z_score = sum(weight*x for weight, x in zip([1.2, 1.4, 3.3, .6, 1.0], z_inputs)) if manufacturer and None not in z_inputs else None
    roa, old_roa = _ratio(now("net_income"), assets), _ratio(old("net_income"), old_assets)
    leverage, old_leverage = _ratio(now("long_term_debt_total"), assets), _ratio(old("long_term_debt_total"), old_assets)
    liquidity = _ratio(now("current_assets"), now("current_liabilities"))
    old_liquidity = _ratio(old("current_assets"), old("current_liabilities"))
    margin, old_margin = _ratio(now("gross_profit"), revenue), _ratio(old("gross_profit"), old_revenue)
    turnover, old_turnover = _ratio(revenue, assets), _ratio(old_revenue, old_assets)
    cfo, income, issuance = now("operating_cash_flow"), now("net_income"), now("common_stock_issuance")

    def criterion(a, b, op):
        return op(a, b) if None not in (a, b) else None

    signals = dict(
        profitable=criterion(roa, 0, gt), positive_cfo=criterion(cfo, 0, gt),
        improved_roa=criterion(roa, old_roa, gt), cash_exceeds_earnings=criterion(cfo, income, gt),
        lower_leverage=criterion(leverage, old_leverage, lt),
        higher_liquidity=criterion(liquidity, old_liquidity, gt),
        no_cash_common_stock_issuance=criterion(issuance, 0, eq),
        improved_margin=criterion(margin, old_margin, gt),
        improved_turnover=criterion(turnover, old_turnover, gt),
    )
    f_score = sum(signals.values()) if None not in signals.values() else None
    dsri = _ratio(_ratio(now("receivables"), revenue), _ratio(old("receivables"), old_revenue))
    gmi = _ratio(old_margin, margin)
    ppe, old_ppe = now("ppe_net"), old("ppe_net")
    aq, old_aq = _ratio(_sum(now("current_assets"), ppe), assets), _ratio(_sum(old("current_assets"), old_ppe), old_assets)
    aqi = _ratio(_change(1, aq), _change(1, old_aq))
    sgi = _ratio(revenue, old_revenue)
    da, old_da = now("depreciation"), old("depreciation")
    depi = _ratio(_ratio(old_da, _sum(old_da, old_ppe)), _ratio(da, _sum(da, ppe)))
    sgai = _ratio(_ratio(now("sga"), revenue), _ratio(old("sga"), old_revenue))
    lvgi = _ratio(_ratio(now("liabilities"), assets), _ratio(old("liabilities"), old_assets))
    tata = _ratio(_change(income, cfo), assets)
    inputs = [dsri, gmi, aqi, sgi, depi, sgai, tata, lvgi]
    m_score = -4.84 + sum(weight*x for weight, x in zip([.92, .528, .404, .892, .115, -.172, 4.679, -.327], inputs)) if None not in inputs else None
    return [
        {"name": name, "value": value if value is not None and isfinite(value) else None,
         "unit": unit, "formula": formula, "status": "available" if value is not None and isfinite(value) else "unavailable"}
        for name, value, unit, formula in (
            ("cash_conversion_cycle", ccc, "days", "365 × (avg inventory / COGS + avg receivables / revenue − avg payables / COGS)"),
            ("altman_z", z_score, "score", "original public-manufacturer coefficients; SEC SIC 2000–3999 only"),
            ("piotroski_f_proxy", f_score, "score", "nine tests, TTM, end-period assets and cash common-stock issuance proxy"),
            ("beneish_m_proxy", m_score, "score", "eight-variable form with total liabilities leverage and available SEC field proxies"),
        )
    ], signals
