"""Daily event simulator: previous completed signal -> next bar open, long-only."""
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, FiniteFloat

from quantcore.strategies.base import BuyHold

MONEY = Decimal('.0001')


def decimal(value):
    return Decimal(str(value))


class ExecutionConfig(BaseModel):
    initial_cash: FiniteFloat = Field(gt=0, default=100_000)
    commission_bps: FiniteFloat = Field(ge=0, le=100, default=1)
    slippage_bps: FiniteFloat = Field(ge=0, le=100, default=2)
    spread_bps: FiniteFloat = Field(ge=0, le=100, default=2)
    impact_bps: FiniteFloat = Field(ge=0, le=100, default=5)
    max_participation: FiniteFloat = Field(gt=0, le=1, default=.01)
    max_weight: FiniteFloat = Field(gt=0, le=1, default=1)
    evaluation_bars: int = Field(ge=2, le=10000, default=252)


@dataclass(frozen=True)
class CorporateAction:
    effective_at: pd.Timestamp
    kind: str
    value: float
    payable_at: pd.Timestamp | None = None
    action_id: str = ''


def performance(equity, returns, fills, initial_cash, benchmark=None):
    values = np.r_[initial_cash, equity]
    total = values[-1]/initial_cash-1
    years = len(returns)/252
    annual = (1+total)**(1/years)-1 if total > -1 else -1.
    std = np.std(returns, ddof=1)
    downside = np.sqrt(np.mean(np.minimum(returns, 0)**2))
    drawdown = values/np.maximum.accumulate(values)-1
    duration = longest = 0
    for value in drawdown:
        duration = duration+1 if value < -1e-12 else 0
        longest = max(longest, duration)
    realized = [f['realized_pnl'] for f in fills if f['side'] == 'sell']
    profits = sum(max(v, 0) for v in realized)
    losses = -sum(min(v, 0) for v in realized)
    result = {'total_return': float(total), 'cagr': float(annual), 'annualized_volatility': float(std*np.sqrt(252)),
        'sharpe': float(np.mean(returns)/std*np.sqrt(252)) if std > 0 else None,
        'sortino': float(np.mean(returns)/downside*np.sqrt(252)) if downside > 0 else None,
        'max_drawdown': float(drawdown.min()), 'drawdown_duration_bars': longest,
        'calmar': float(annual/-drawdown.min()) if drawdown.min() < 0 else None,
        'fills': len(fills), 'closed_fills': len(realized),
        'win_rate': float(np.mean(np.array(realized) > 0)) if realized else None,
        'profit_factor': profits/losses if losses > 0 else None,
        'turnover': sum(f['notional'] for f in fills)/float(np.mean(values)),
        'total_cost': sum(f['total_cost'] for f in fills)}
    if benchmark is not None:
        active = returns-benchmark
        variance = np.var(benchmark, ddof=1)
        beta = float(np.cov(returns, benchmark, ddof=1)[0, 1]/variance) if variance > 0 else None
        tracking = float(active.std(ddof=1)*np.sqrt(252))
        result.update(beta=beta, alpha=float((returns.mean()-beta*benchmark.mean())*252) if beta is not None else None,
                      tracking_error=tracking, information_ratio=float(active.mean()*252/tracking) if tracking > 0 else None,
                      benchmark_relative_return=float(np.prod(1+returns)/np.prod(1+benchmark)-1))
    return result


def simulate(frame, strategy, config=None, actions=()):
    config = config or ExecutionConfig()
    if len(frame) < 3 or not frame.index.is_monotonic_increasing or frame.index.has_duplicates:
        raise ValueError('unique chronological history required')
    if not np.isfinite(frame[['open', 'high', 'low', 'close', 'volume']]).all().all() or (frame[['open', 'close']] <= 0).any().any():
        raise ValueError('invalid prices')
    if frame.get('currency', pd.Series(['USD'])).nunique() != 1:
        raise ValueError('mixed currencies need explicit FX conversion')
    mode = str(frame['mode'].iloc[0]) if 'mode' in frame else 'synthetic'
    if 'mode' in frame and frame['mode'].nunique() != 1:
        raise ValueError('mixed market data modes')
    if mode not in ('synthetic', 'historical'):
        raise ValueError('backtests require synthetic or historical data')
    if mode == 'historical' and not {'execution_open', 'signal_close'}.issubset(frame):
        raise ValueError('historical data requires actual session opens and causal signal prices')
    signal_frame = frame.copy()
    if 'signal_close' in frame:
        signal_frame['close'] = frame.signal_close
    signals = strategy.targets(signal_frame)
    if not signals.index.equals(frame.index) or not np.isfinite(signals).all() or ((signals < 0) | (signals > config.max_weight)).any():
        raise ValueError('invalid target weights')
    start = max(1, len(frame)-config.evaluation_bars)
    cash, quantity, basis = decimal(config.initial_cash), 0, Decimal(0)
    fills, curve, consumed, delisted = [], [], set(), False
    receivables = []
    first_open = pd.Timestamp(frame.iloc[start].execution_open) if mode == 'historical' else None
    if first_open is not None:
        consumed = {i for i, action in enumerate(actions) if action.effective_at < first_open and action.kind != 'delisting'}
    old_equity = config.initial_cash
    for i in range(start, len(frame)):
        stamp = frame.index[i]
        row, previous = frame.iloc[i], frame.iloc[i-1]
        execution_at = pd.Timestamp(row.execution_open) if mode == 'historical' else stamp-pd.Timedelta(hours=6, minutes=30)
        if execution_at.tzinfo is None or execution_at >= stamp:
            raise ValueError('execution must precede its session close and be timezone-aware')
        if pd.Timestamp(previous.available_at) >= execution_at:
            raise ValueError('signal was unavailable before execution')
        action_cash = Decimal(0)
        split_today = Decimal(1)
        for n, action in enumerate(actions):
            if n in consumed or action.effective_at > execution_at:
                continue
            if not np.isfinite(action.value) or action.value < 0:
                raise ValueError('invalid corporate action')
            if action.kind == 'split':
                new_quantity = decimal(quantity)*decimal(action.value)
                if action.value <= 0 or new_quantity != new_quantity.to_integral():
                    raise ValueError('fractional split needs an explicit cash-in-lieu price')
                quantity = int(new_quantity)
                basis = basis/decimal(action.value)
                split_today *= decimal(action.value)
            elif action.kind == 'dividend':
                amount = (decimal(quantity)*decimal(action.value)).quantize(MONEY)
                if mode == 'historical':
                    if action.payable_at is None or action.payable_at < action.effective_at:
                        raise ValueError('historical dividends require valid cash availability dates')
                    receivables.append((action.payable_at, amount))
                else:
                    action_cash += amount
            elif action.kind == 'delisting':
                action_cash += decimal(quantity)*decimal(action.value)
                quantity, basis, delisted = 0, Decimal(0), True
            else:
                raise ValueError('unsupported corporate action')
            consumed.add(n)
        paid = sum((amount for payment, amount in receivables if payment <= execution_at), Decimal(0))
        receivables = [(payment, amount) for payment, amount in receivables if payment > execution_at]
        pending = sum((amount for _, amount in receivables), Decimal(0))
        action_cash += paid
        cash += action_cash
        opening = decimal(row.open)
        nav = cash+quantity*opening+pending
        target = 0 if delisted else int((decimal(signals.iloc[i-1])*nav/opening).to_integral_value(rounding=ROUND_FLOOR))
        difference = target-quantity
        capacity = int(decimal(previous.volume)*split_today*decimal(config.max_participation))
        reference_volume = float(decimal(previous.volume)*split_today)
        size = min(abs(difference), capacity)
        if size:
            side = 1 if difference > 0 else -1
            bps = config.slippage_bps+config.spread_bps/2+config.impact_bps*np.sqrt(size/max(reference_volume, 1))
            price = opening*(1+decimal(side*bps/10000))
            if side > 0:
                affordable = int((cash/(price*(1+decimal(config.commission_bps/10000)))).to_integral_value(rounding=ROUND_FLOOR))
                size = min(size, affordable)
            if size:
                notional = (size*price).quantize(MONEY)
                fee = (notional*decimal(config.commission_bps/10000)).quantize(MONEY)
                realized = float(notional-fee-size*basis) if side < 0 else 0.
                if side > 0:
                    basis = (basis*quantity+notional+fee)/(quantity+size)
                cash -= side*notional+fee
                quantity += side*size
                if cash < 0 or quantity < 0:
                    raise RuntimeError('cash or inventory invariant violated')
                fills.append({'timestamp': execution_at.isoformat(),
                    'signal_at': pd.Timestamp(previous.available_at).isoformat() if mode == 'historical' else frame.index[i-1].isoformat(),
                    'side': 'buy' if side > 0 else 'sell', 'quantity': size, 'price': float(price), 'notional': float(notional),
                    'commission': float(fee), 'total_cost': float(abs(price-opening)*size+fee),
                    'cash_after': str(cash), 'inventory_after': quantity, 'realized_pnl': realized,
                    'partial_fill': size < abs(difference), 'volume_reference': 'previous completed bar'})
        equity = float(cash+quantity*decimal(row.close)+pending)
        curve.append({'timestamp': stamp.isoformat(), 'equity': equity, 'cash': str(cash), 'quantity': quantity,
                      'return': equity/old_equity-1, 'corporate_action_cash': str(action_cash),
                      'dividend_receivable': str(pending), 'dividend_cash_paid': str(paid)})
        old_equity = equity
    equities = np.array([r['equity'] for r in curve])
    returns = np.array([r['return'] for r in curve])
    return {'strategy': strategy.name, 'config': config.model_dump(), 'curve': curve, 'fills': fills,
            'metrics': performance(equities, returns, fills, config.initial_cash), 'mode': mode,
            'period': {'start': curve[0]['timestamp'], 'end': curve[-1]['timestamp']},
            'assumptions': ['long-only integer shares; no margin/borrow/funding',
                            'XNYS sessions; first observed regular-session IEX minute open' if mode == 'historical' else 'synthetic daily UTC calendar',
                            'signal at previous close; next open fill', 'volume cap uses previous completed bar in current share units',
                            'simulated spread/impact; not reconstructed order book', 'open positions marked to final close']}


def backtest(frame, strategy, config=None, actions=()):
    config = config or ExecutionConfig()
    result = simulate(frame, strategy, config, actions)
    gross_config = config.model_copy(update=dict(commission_bps=0, slippage_bps=0, spread_bps=0, impact_bps=0))
    gross = simulate(frame, strategy, gross_config, actions)
    benchmark = simulate(frame, BuyHold(), config, actions)
    returns = np.array([r['return'] for r in result['curve']])
    benchmark_returns = np.array([r['return'] for r in benchmark['curve']])
    result['metrics'] = performance(np.array([r['equity'] for r in result['curve']]), returns, result['fills'], config.initial_cash, benchmark_returns)
    result['gross_metrics'] = gross['metrics']
    result['benchmark_metrics'] = benchmark['metrics']
    for current, reference in zip(result['curve'], benchmark['curve']):
        current['benchmark_equity'] = reference['equity']
    return result
