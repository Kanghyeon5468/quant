"""Independent long-only pretrade limits; no broker, strategy or optimizer imports."""
import hashlib
import json

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field


class RiskLimits(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid', allow_inf_nan=False, validate_default=True)
    daily_loss: float = Field(default=.02, gt=0, le=1)
    drawdown: float = Field(default=.10, gt=0, le=1)
    gross_weight: float = Field(default=.95, gt=0, le=1)
    position_weight: float = Field(default=.20, gt=0, le=1)
    sector_weight: float = Field(default=.40, gt=0, le=1)
    correlated_weight: float = Field(default=.40, gt=0, le=1)
    correlation_threshold: float = Field(default=.80, gt=0, le=1)
    portfolio_volatility: float = Field(default=.25, gt=0, le=5)
    adv_participation: float = Field(default=.01, gt=0, le=1)
    sectors: dict[str, str] = Field(default_factory=dict)

    @property
    def version(self):
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True).encode()).hexdigest()[:16]


def account_state(previous, equity, previous_close_equity, budget, day, identity):
    if not all(np.isfinite(x) and x > 0 for x in (equity, previous_close_equity, budget)):
        raise ValueError('risk needs positive broker equity, previous-close equity and budget')
    if previous and previous['account_hash'] != identity:
        raise ValueError('risk state belongs to a different account')
    initial = previous.get('initial_account_equity', equity)
    nav = budget+equity-initial
    adjustment = budget-previous.get('budget', budget)
    peak = max(previous.get('peak', nav)+adjustment, nav)
    same_day = previous.get('day') == day
    start = previous['daily_start']+adjustment if same_day else budget+previous_close_equity-initial
    if nav <= 0 or start <= 0:
        raise ValueError('nonpositive strategy NAV')
    return {**previous, 'account_hash': identity, 'initial_account_equity': initial,
            'budget': budget, 'day': day, 'daily_start': start, 'peak': peak, 'last_equity': nav,
            'daily_latched': previous.get('daily_latched', False) if same_day else False,
            'drawdown_latched': previous.get('drawdown_latched', False)}


def features(histories, as_of):
    cut = pd.Timestamp(as_of)
    if cut.tzinfo is None:
        raise ValueError('risk cutoff must be timezone-aware')
    returns, adv, prices = {}, {}, {}
    for symbol, history in histories.items():
        f = history[history.available_at <= cut].tail(61)
        if len(f) < 60 or 'volume' not in f:
            raise ValueError('risk needs >=60 available sessions and observed volume')
        values = f[['signal_close', 'close', 'volume']].to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values[:, :2] <= 0).any() or (values[:, 2] < 0).any():
            raise ValueError('invalid risk market data')
        returns[symbol] = pd.Series(f.signal_close.pct_change().to_numpy(), index=pd.to_datetime(f.timestamp if 'timestamp' in f else f.index, utc=True))
        adv[symbol], prices[symbol] = float(f.volume.tail(20).mean()), float(f.close.iloc[-1])
    matrix = pd.DataFrame(returns).dropna().tail(60)
    if len(matrix) < 59:
        raise ValueError('risk histories are not aligned')
    vol = matrix.tail(20).std(ddof=1).to_numpy()*np.sqrt(252)
    corr = matrix.corr().to_numpy()
    # Constant return histories have no covariance; missing correlations do not imply diversification.
    for i in range(len(vol)):
        for j in range(len(vol)):
            if not np.isfinite(corr[i, j]):
                corr[i, j] = 0. if vol[i] < 1e-12 or vol[j] < 1e-12 else 1.
    np.fill_diagonal(corr, 1.)
    return {'symbols': list(matrix.columns), 'prices': prices, 'adv20': adv,
            'volatility20': dict(zip(matrix.columns, vol.tolist())), 'correlation60': corr.tolist(),
            'covariance': (corr*np.outer(vol, vol)).tolist(), 'as_of': cut.isoformat()}


def exposure(feature, values, equity, limits):
    if not np.isfinite(equity) or equity <= 0:
        raise ValueError('positive risk equity required')
    symbols = feature['symbols']
    weights = np.array([max(0., float(values.get(s, 0)))/equity for s in symbols])
    sector = {}
    for s, w in zip(symbols, weights):
        name = limits.sectors.get(s) or 'UNCLASSIFIED'
        sector[name] = sector.get(name, 0.)+float(w)
    corr = np.asarray(feature['correlation60'])
    remaining, clusters = set(range(len(symbols))), []
    while remaining:
        group, queue = set(), [min(remaining)]
        while queue:
            i = queue.pop()
            if i in group:
                continue
            group.add(i)
            queue.extend(j for j in remaining-group if corr[i, j] >= limits.correlation_threshold)
        remaining -= group
        if len(group) > 1:
            clusters.append({'symbols': [symbols[i] for i in sorted(group)], 'weight': float(sum(weights[i] for i in group))})
    covariance = np.asarray(feature['covariance'])
    volatility = float(np.sqrt(max(0., weights@covariance@weights)))
    measures = {'gross_weight': float(weights.sum()), 'position_weights': dict(zip(symbols, weights.tolist())),
                'sector_weights': sector, 'correlated_groups': clusters, 'portfolio_volatility': volatility}
    violations = []
    if measures['gross_weight'] > limits.gross_weight+1e-10:
        violations.append('gross_weight')
    if any(w > limits.position_weight+1e-10 for w in weights):
        violations.append('position_weight')
    if any(w > limits.sector_weight+1e-10 for w in sector.values()):
        violations.append('sector_weight')
    if any(c['weight'] > limits.correlated_weight+1e-10 for c in clusters):
        violations.append('correlated_weight')
    if volatility > limits.portfolio_volatility+1e-10:
        violations.append('portfolio_volatility')
    return measures, violations


def filter_orders(feature, inventory, marks, pending, orders, equity, daily_start, peak, limits,
                  daily_latched=False, drawdown_latched=False):
    daily_return, drawdown = equity/daily_start-1, equity/peak-1
    halt = []
    if daily_latched or daily_return <= -limits.daily_loss:
        halt.append('daily_loss')
    if drawdown_latched or drawdown <= -limits.drawdown:
        halt.append('drawdown')
    values = {s: float(inventory.get(s, 0))*float(marks.get(s, feature['prices'][s])) for s in feature['symbols']}
    before, base_violations = exposure(feature, values, equity, limits)
    accepted, rejected, cancel = [], [], []
    pending_qty = dict.fromkeys(feature['symbols'], 0)
    for order in pending:
        if order['side'] != 'buy':
            continue
        s, qty = order['symbol'], int(order['remaining_qty'])
        proposal = {**values, s: values[s]+qty*float(order['limit_price'])}
        _, violations = exposure(feature, proposal, equity, limits)
        if qty+pending_qty[s] > feature['adv20'][s]*limits.adv_participation:
            violations.append('liquidity')
        if halt or base_violations or violations:
            cancel.append({'client_order_id': order['client_order_id'], 'symbol': s,
                           'rules': sorted(set(halt+base_violations+violations))})
        else:
            values = proposal
            pending_qty[s] += qty
    for order in orders:
        if order['side'] == 'sell':
            if int(order['qty']) > inventory.get(order['symbol'], 0):
                raise ValueError('risk-reducing sale exceeds owned quantity')
            accepted.append(order)
            continue  # No cash/exposure credit for an unfilled sale.
        s, requested = order['symbol'], int(order['qty'])
        unit = float(order['limit_price'])
        liquidity = max(0, int(feature['adv20'][s]*limits.adv_participation)-pending_qty[s])
        upper = min(requested, liquidity)
        rules = list(halt+base_violations)
        def check(qty):
            return exposure(feature, {**values, s: values[s]+qty*unit}, equity, limits)[1]
        if rules:
            upper = 0
        else:
            rules.extend(check(upper))
            lo, hi = 0, upper
            while lo < hi:
                mid = (lo+hi+1)//2
                if check(mid):
                    hi = mid-1
                else:
                    lo = mid
            upper = lo
        if upper < requested:
            if liquidity < requested:
                rules.append('liquidity')
            rejected.append({'symbol': s, 'requested_qty': requested, 'approved_qty': upper,
                             'rules': sorted(set(rules))})
        if upper:
            accepted.append({**order, 'qty': str(upper)})
            values[s] += upper*unit
            pending_qty[s] += upper
    after, _ = exposure(feature, values, equity, limits)
    return {'orders': accepted, 'rejected': rejected, 'cancel_pending': cancel,
            'halt_rules': halt, 'current_violations': base_violations,
            'daily_return': daily_return, 'drawdown': drawdown, 'current': before, 'projected': after,
            'risk_policy_version': limits.version, 'limits': limits.model_dump(),
            'sector_basis': 'configured groups; missing sector data grouped conservatively as UNCLASSIFIED',
            'sector_unclassified': [s for s in feature['symbols'] if not limits.sectors.get(s)]}
