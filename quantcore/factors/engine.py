import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from quantcore.fundamentals.analysis import analyze


def factor_scores(store, as_of, weights=None, sector_neutral=False):
    rows = []
    for asset in store.asset_list():
        frame = store.prices(asset['symbol'], as_of)
        facts = store.fundamentals(asset['symbol'], as_of)
        if len(frame) < 253 or not facts:
            continue
        current = facts[-1]
        metrics = {m['name']: m['value'] for m in analyze(facts)['metrics']}
        cap = asset['market_cap']  # Synthetic fixed reference cap, not a live estimate.
        rows.append({'symbol': asset['symbol'], 'sector': asset['sector'], 'value': current['equity']/cap,
            'momentum': frame.close.iloc[-22]/frame.close.iloc[-253]-1,
            'quality': metrics['roe'], 'growth': metrics['revenue_growth'],
            'low_volatility': -frame.close.pct_change().tail(63).std()*np.sqrt(252),
            'liquidity': np.log((frame.close*frame.volume).tail(20).mean())})
    if not rows:
        return []
    frame = pd.DataFrame(rows).set_index('symbol')
    names = ['value', 'momentum', 'quality', 'growth', 'low_volatility', 'liquidity']
    weights = weights or dict.fromkeys(names, 1.)
    if set(weights)-set(names) or any(not np.isfinite(v) or v < 0 for v in weights.values()) or sum(weights.values()) <= 0:
        raise ValueError('nonnegative finite factor weights with positive sum required')
    total = pd.Series(0., index=frame.index)
    for name in names:
        values = frame[name].clip(frame[name].quantile(.05), frame[name].quantile(.95))
        if sector_neutral:
            values = values-values.groupby(frame.sector).transform('mean')
        std = values.std(ddof=0)
        z = (values-values.mean())/std if std > 1e-12 else values*0
        frame[name+'_z'] = z
        total += z*weights.get(name, 0)/sum(weights.values())
    frame['score'] = total
    frame['rank'] = total.rank(ascending=False, method='min').astype(int)
    frame['as_of'] = str(as_of)
    frame['mode'] = 'synthetic'
    return frame.reset_index().sort_values('rank').to_dict('records')


def rank_ic(scores, future_returns):
    paired = pd.concat([scores, future_returns], axis=1).dropna()
    if len(paired) < 3 or paired.iloc[:, 0].nunique() < 2 or paired.iloc[:, 1].nunique() < 2:
        return None
    return float(spearmanr(paired.iloc[:, 0], paired.iloc[:, 1]).statistic)
