"""Ratios return missing/unsupported states rather than fabricated zeroes."""
import math


def analyze(records):
    if not records:
        return {'status': 'missing', 'metrics': []}
    current, prior = records[-1], records[-2] if len(records) > 1 else {}
    metrics = []

    def add(name, numerator, denominator, formula, unit='ratio'):
        valid = numerator is not None and denominator is not None and denominator > 0
        value = numerator/denominator if valid else None
        if value is not None and not math.isfinite(value):
            value = None
        metrics.append({'name': name, 'value': value, 'unit': unit,
                        'status': 'ok' if value is not None else 'not_applicable', 'formula': formula,
                        'period_end': current['period_end'], 'published_at': current['published_at'],
                        'available_at': current['available_at'], 'source': current['source'],
                        'source_url': current.get('source_url'), 'mode': current['mode']})

    get = current.get
    def difference(a, b):
        return a-b if a is not None and b is not None else None

    def average(key):
        return (get(key)+prior[key])/2 if get(key) is not None and key in prior else None
    for name, key in [('revenue_growth', 'revenue'), ('eps_growth', 'eps'), ('fcf_growth', 'fcf')]:
        now = get(key)
        before = prior.get(key)
        if key == 'eps':
            now = get('net_income')/get('shares') if get('shares', 0) > 0 else None
            before = prior.get('net_income', 0)/prior['shares'] if prior.get('shares', 0) > 0 else None
        if key == 'fcf':
            now = difference(get('operating_cash_flow'), get('capex'))
            before = difference(prior.get('operating_cash_flow'), prior.get('capex'))
        add(name, difference(now, before), before, '(current-prior)/prior; prior must be positive')
    for name, numerator in [('gross_margin', 'gross_profit'), ('operating_margin', 'operating_income'), ('net_margin', 'net_income')]:
        add(name, get(numerator), get('revenue'), f'{numerator}/revenue')
    add('roe', get('net_income'), average('equity'), 'net income / average equity')
    add('roa', get('net_income'), average('assets'), 'net income / average assets')
    add('asset_turnover', get('revenue'), average('assets'), 'revenue / average assets')
    fcf = difference(get('operating_cash_flow'), get('capex'))
    add('free_cash_flow', fcf, 1, 'operating cash flow - capital expenditure', get('currency'))
    ebitda = get('operating_income', 0)+get('depreciation', 0) if all(k in current for k in ['operating_income', 'depreciation']) else None
    add('ebitda', ebitda, 1, 'EBIT + depreciation and amortization', get('currency'))
    nonfinancial = current.get('industry') == 'nonfinancial'
    invested = get('equity', 0)+get('debt', 0)-get('cash', 0) if nonfinancial else None
    nopat = get('operating_income', 0)*(1-get('tax_rate', 0)) if 'tax_rate' in current else None
    add('roic', nopat, invested, 'NOPAT / (equity + debt - cash); nonfinancial end-period approximation')
    add('debt_to_equity', get('debt') if nonfinancial else None, get('equity'), 'interest-bearing debt / equity; nonfinancial')
    add('current_ratio', get('current_assets') if nonfinancial else None, get('current_liabilities'), 'current assets/current liabilities')
    add('interest_coverage', get('operating_income') if nonfinancial else None, get('interest_expense'), 'EBIT/interest expense')
    add('accrual_ratio', difference(get('net_income'), get('operating_cash_flow')), average('assets'), '(net income-CFO)/average assets')
    add('share_dilution', difference(get('shares'), prior.get('shares')), prior.get('shares'), '(shares-current minus prior)/prior')
    return {'status': 'ok', 'currency': get('currency'), 'mode': get('mode'), 'metrics': metrics,
            'unsupported': ['cash_conversion_cycle', 'altman_z', 'piotroski_f', 'beneish_m'],
            'limitations': ['annual periods only in demo; no TTM reconstruction', 'missing or industry-inapplicable metrics remain null']}
