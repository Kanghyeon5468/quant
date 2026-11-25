"""One cash ledger, fixed slots, DAY limits and observable-minute risk replay.

This is a conservative OHLC/volume model, not a reconstruction of Alpaca's NBBO
matching, queue priority or random partial fills. No dividend credit (paper parity).
"""
import gzip
import hashlib
import json
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path

import numpy as np
import pandas as pd

from quantcore.data.calendar import sessions
from quantcore.data.providers.alpaca import SYMBOLS, load_snapshot
from quantcore.risk.limits import RiskLimits, account_state, features, filter_orders
from quantcore.strategies.orders import OrderPolicy, modeled_cost, money, slot_orders


def load_minutes(snapshot):
    """Verify original response pages and reconcile observed RTH bars to daily inputs."""
    snapshot = Path(snapshot)
    daily, actions, manifest = load_snapshot(snapshot)
    if manifest.get('source') != 'alpaca-iex-regular-1min' or not manifest.get('raw_pages'):
        raise ValueError('verified actual minute pages required; no synthetic fallback')
    parts = []
    for item in manifest['raw_pages']:
        name = item['name']
        if Path(name).name != name:
            raise ValueError('unsafe raw-page path')
        raw = gzip.decompress((snapshot/name).read_bytes())
        if hashlib.sha256(raw).hexdigest() != item['sha256_uncompressed']:
            raise ValueError('raw minute hash mismatch')
        for symbol, rows in json.loads(raw)['bars'].items():
            if rows:
                parts.append(pd.DataFrame(rows).assign(symbol=symbol))
    frame = pd.concat(parts, ignore_index=True)
    frame['timestamp'] = pd.to_datetime(frame.t, utc=True)
    frame['session'] = frame.timestamp.dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d')
    schedule = sessions(manifest['start'], manifest['end'])
    frame = frame.merge(schedule.rename(columns={'open': 'session_open', 'close': 'session_close'}),
                        left_on='session', right_index=True, how='inner')
    frame = frame[(frame.timestamp >= frame.session_open) &
                  (frame.timestamp+pd.Timedelta(minutes=1) <= frame.session_close)]
    frame = frame.sort_values(['timestamp', 'symbol']).reset_index(drop=True)
    validate_minutes(daily, frame)
    daily.attrs['split_actions'] = [{'symbol':s,'session':a.effective_at.tz_convert('America/New_York').date().isoformat(),
        'ratio':str(a.value),'action_id':a.action_id} for s,group in actions.items() for a in group if a.kind == 'split']
    return daily, frame, manifest


def validate_minutes(daily, minutes):
    if minutes.duplicated(['symbol', 'timestamp']).any():
        raise ValueError('duplicate minute observation')
    values = minutes[['o', 'h', 'l', 'c', 'v']].to_numpy(dtype=float)
    if (not np.isfinite(values).all() or (values[:, :4] <= 0).any() or (values[:, 4] < 0).any()
            or (values[:, 4] % 1 != 0).any()
            or (values[:, 1] < values[:, [0, 2, 3]].max(axis=1)).any()
            or (values[:, 2] > values[:, [0, 1, 3]].min(axis=1)).any()):
        raise ValueError('invalid minute OHLC/volume')
    agg = minutes.sort_values('timestamp').groupby(['symbol', 'session']).agg(
        open=('o', 'first'), high=('h', 'max'), low=('l', 'min'), close=('c', 'last'), volume=('v', 'sum'))
    expected = daily.set_index(['symbol', 'session'])[list(agg.columns)].sort_index()
    if not agg.index.equals(expected.index) or not np.allclose(agg, expected, rtol=0, atol=1e-8):
        raise ValueError('minute inputs disagree with frozen daily history')


def match_limit(order, bar, policy, adv, cash, inventory):
    """No invented bars; fills at observed bar end; price stays inside OHLC and limit."""
    side, limit = order['side'], money(order['limit_price'])
    if (side == 'buy' and money(bar.l) > limit) or (side == 'sell' and money(bar.h) < limit):
        return None
    qty = min(order['remaining'], int(money(bar.v)*money(policy.minute_participation)))
    if not qty:
        return None
    cost = modeled_cost(order['reference'], int(order['qty']), adv, policy)
    adverse = money(cost['adverse_bps'])/10000
    base = min(money(bar.o), limit) if side == 'buy' else max(money(bar.o), limit)
    price = min(limit, money(bar.h), base*(1+adverse)) if side == 'buy' else max(limit, money(bar.l), base*(1-adverse))
    unit_fee = price*money(policy.commission_bps)/10000
    if side == 'buy':
        qty = min(qty, int((cash/(price+unit_fee)).to_integral_value(rounding=ROUND_FLOOR)))
    else:
        qty = min(qty, inventory)
    if qty <= 0:
        return None
    fee = (qty*unit_fee).quantize(Decimal('.00000001'))
    return qty, price, fee, abs(price-base)*qty


def replay(daily, minutes, strategy='momentum', budget=100000, evaluation_sessions=252,
           policy=None, limits=None, risk_enabled=True, strategy_by_day=None):
    policy, limits = policy or OrderPolicy(), limits or RiskLimits()
    budget = money(budget)
    if budget <= 0:
        raise ValueError('positive portfolio budget required')
    symbols = [s for s in SYMBOLS if s in set(daily.symbol)]+sorted(set(daily.symbol)-set(SYMBOLS))
    days = sorted(daily.session.unique())
    if len(days) < evaluation_sessions+60:
        raise ValueError('60 prior sessions required before portfolio evaluation')
    eval_days = days[-evaluation_sessions:]
    schedule = sessions(eval_days[0], eval_days[-1])
    cash, previous_equity = budget, float(budget)
    inventory = dict.fromkeys(symbols, 0)
    state, curve, fills, orders_log, risk_log = {}, [], [], [], []
    groups = dict(tuple(minutes.groupby('session', sort=False)))
    histories_all = {s: g.sort_values('timestamp') for s, g in daily.groupby('symbol')}
    min_cash, min_inventory = cash, 0
    split_actions = daily.attrs.get('split_actions', [])
    for symbol, history in histories_all.items():
        if (history.signal_close/history.close).round(8).nunique()>1 and not any(a['symbol']==symbol for a in split_actions):
            raise ValueError('verified split actions required for changing share units')
    corporate_log = []
    for day in eval_days:
        clock = schedule.loc[day]
        histories = {s: histories_all[s][histories_all[s].available_at < clock['open']] for s in symbols}
        if any(len(f) < 60 for f in histories.values()):
            raise ValueError('insufficient available signal history')
        day_adjustments = {}
        for action in split_actions:
            if action['session'] != day:
                continue
            symbol, ratio = action['symbol'], money(action['ratio'])
            replacement = money(inventory[symbol])*ratio
            if ratio <= 0 or replacement != replacement.to_integral_value():
                raise ValueError('fractional split requires verified cash-in-lieu; no invented settlement')
            delta = int(replacement)-inventory[symbol]
            inventory[symbol] = int(replacement)
            day_adjustments[symbol] = day_adjustments.get(symbol, 0)+delta
            histories[symbol] = histories[symbol].copy()
            histories[symbol]['close'] /= float(ratio)
            corporate_log.append({**action, 'timestamp':str(clock['open']), 'quantity_delta':delta,
                                  'quantity_after':inventory[symbol], 'cash_delta':'0',
                                  'basis':'mechanical effective split; not a pre-publication signal'})
        # Convert historical volumes into the share units applicable at this session open.
        for symbol, history in histories.items():
            histories[symbol] = history.copy()
            visible = history.signal_close/histories_all[symbol].loc[history.index, 'close']
            current = float(visible.iloc[-1])
            for action in split_actions:
                if action['symbol'] == symbol and action['session'] == day:
                    current *= float(action['ratio'])
            histories[symbol]['volume'] = history.volume*current/visible
        marks = {s: float(f.close.iloc[-1]) for s, f in histories.items()}
        feature = features(histories, clock['open'])
        chosen_strategy = strategy_by_day[day] if strategy_by_day is not None else strategy
        allocation = slot_orders(histories, inventory, cash, budget, chosen_strategy, policy=policy)
        state = account_state(state, previous_equity, previous_equity, float(budget), day, 'portfolio-replay')
        def risk_check(stamp, pending, candidates):
            nav = float(cash+sum((money(marks[s])*q for s, q in inventory.items()), Decimal(0)))
            state['peak'] = max(state['peak'], nav)
            report = filter_orders(feature, inventory, marks, pending, candidates, nav,
                state['daily_start'], state['peak'], limits, state['daily_latched'], state['drawdown_latched'])
            state['daily_latched'] |= 'daily_loss' in report['halt_rules']
            state['drawdown_latched'] |= 'drawdown' in report['halt_rules']
            for rule in sorted(set(report['halt_rules']+report['current_violations'])):
                key = (day, rule, 'PORTFOLIO')
                if key not in seen:
                    seen.add(key)
                    risk_log.append({'timestamp': str(stamp), 'session': day, 'rule': rule, 'symbol': 'PORTFOLIO'})
            for rejection in report['rejected']+report['cancel_pending']:
                for rule in rejection['rules']:
                    key = (day, rule, rejection['symbol'])
                    if key not in seen:
                        seen.add(key)
                        risk_log.append({'timestamp': str(stamp), 'session': day, 'rule': rule, 'symbol': rejection['symbol']})
            return report
        seen = set()
        selected = allocation['orders']
        if risk_enabled:
            selected = risk_check(clock['open'], [], selected)['orders']
        pending = []
        for n, order in enumerate(selected):
            record = {**order, 'client_order_id': f'replay-{day}-{n}-{order["symbol"]}',
                'remaining': int(order['qty']), 'reference': allocation['references'][order['symbol']]['reference_close'],
                'signal_at': str(histories[order['symbol']].available_at.iloc[-1]),
                'created_at': str(clock['open']), 'session': day, 'status': 'accepted', 'filled_qty': 0}
            orders_log.append(record)
            pending.append(record)
        observed = groups.get(day)
        if observed is None or set(observed.symbol) != set(symbols):
            raise ValueError('missing regular-session observations; cannot validate this day')
        for stamp, bars in observed.groupby('timestamp', sort=True):
            by_symbol = {b.symbol: b for b in bars.itertuples()}
            for order in list(pending):
                s = order['symbol']
                if s not in by_symbol:
                    continue
                fill = match_limit(order, by_symbol[s], policy, feature['adv20'][s], cash, inventory[s])
                if fill:
                    qty, price, fee, friction = fill
                    signed = qty if order['side'] == 'buy' else -qty
                    cash -= signed*price+fee
                    inventory[s] += signed
                    order['remaining'] -= qty
                    order['filled_qty'] += qty
                    order['status'] = 'filled' if not order['remaining'] else 'partially_filled'
                    fills.append({'symbol': s, 'session': day, 'timestamp': str(stamp+pd.Timedelta(minutes=1)),
                        'signal_at': order['signal_at'], 'side': order['side'], 'quantity': qty,
                        'price': float(price), 'limit_price': float(order['limit_price']),
                        'notional': str(qty*price), 'commission': str(fee), 'modeled_execution_cost': str(friction)})
                    if not order['remaining']:
                        pending.remove(order)
                    min_cash, min_inventory = min(min_cash, cash), min(min_inventory, inventory[s])
            for s, bar in by_symbol.items():
                marks[s] = float(bar.c)
            end = stamp+pd.Timedelta(minutes=1)
            if risk_enabled and (int((end-clock['open']).total_seconds()/60) % 5 == 0 or end == clock['close']):
                own_pending = [{**o, 'remaining_qty': str(o['remaining'])} for o in pending]
                veto = risk_check(end, own_pending, [])['cancel_pending']
                cancel = {o['client_order_id'] for o in veto}
                for order in list(pending):
                    if order['client_order_id'] in cancel:
                        order['status'] = 'canceled_risk'
                        pending.remove(order)
        for order in pending:
            order['status'] = 'expired'
        expected = {s: float(histories_all[s].loc[histories_all[s].session == day, 'close'].iloc[0]) for s in symbols}
        if marks != expected:
            raise ValueError('closing mark does not reconcile to daily data')
        equity = cash+sum((money(marks[s])*q for s, q in inventory.items()), Decimal(0))
        if min_cash < 0 or min_inventory < 0 or equity <= 0:
            raise AssertionError('portfolio cash/inventory invariant failed')
        previous_equity = float(equity)
        curve.append({'session': day, 'timestamp': str(clock['close']), 'equity': float(equity), 'cash': str(cash),
                      'gross_weight': float((equity-cash)/equity), 'holdings': dict(inventory),
                      'corporate_quantity_deltas': day_adjustments, 'strategy': chosen_strategy, 'daily_latched': state['daily_latched'], 'drawdown_latched': state['drawdown_latched']})
    ledger_audit(curve, fills, daily, budget, symbols)
    values = np.array([float(budget)]+[r['equity'] for r in curve])
    returns = values[1:]/values[:-1]-1
    dd = values/np.maximum.accumulate(values)-1
    metrics = {'total_return': values[-1]/values[0]-1, 'final_equity': values[-1],
               'max_drawdown': float(dd.min()), 'annualized_volatility': float(np.std(returns, ddof=1)*np.sqrt(252)),
               'sharpe': float(returns.mean()/returns.std(ddof=1)*np.sqrt(252)) if returns.std(ddof=1) else 0.,
               'filled_shares': sum(r['quantity'] for r in fills), 'fill_events': len(fills), 'orders': len(orders_log),
               'expired_orders': sum(o['status'] == 'expired' for o in orders_log),
               'risk_canceled_orders': sum(o['status'] == 'canceled_risk' for o in orders_log),
               'risk_events': len(risk_log),
               'commission': float(sum((money(r['commission']) for r in fills), Decimal(0))),
               'modeled_execution_cost': float(sum((money(r['modeled_execution_cost']) for r in fills), Decimal(0))),
               'average_gross_weight': float(np.mean([r['gross_weight'] for r in curve]))}
    return {'metrics': metrics, 'curve': curve, 'fills': fills, 'corporate_actions': corporate_log, 'orders': orders_log, 'risk_events': risk_log,
            'audit': {'min_cash': str(min_cash), 'min_inventory': min_inventory,
                      'signal_before_fill': all(pd.Timestamp(f['signal_at']) < pd.Timestamp(f['timestamp']) for f in fills),
                      'limit_respected': all(f['price'] <= f['limit_price'] if f['side'] == 'buy' else f['price'] >= f['limit_price'] for f in fills),
                      'sessions': len(curve), 'cash_inventory_nav_reconciled': True, 'split_events': len(corporate_log)},
            'config': {'budget': str(budget), 'slots': len(symbols), 'strategy': strategy, 'risk_enabled': risk_enabled,
                       'order_policy': policy.model_dump(), 'order_policy_version': policy.version,
                       'risk_limits': limits.model_dump(), 'risk_policy_version': limits.version,
                       'strategy_schedule': strategy_by_day,
                       'dividends': 'not credited: Alpaca paper parity', 'risk_poll_minutes': 5}}


def ledger_audit(curve, fills, daily, budget, symbols):
    cash = money(budget)
    inventory = dict.fromkeys(symbols, 0)
    fill_days = {}
    for fill in fills:
        fill_days.setdefault(fill['session'], []).append(fill)
    marks = daily.set_index(['session', 'symbol']).close
    for row in curve:
        for symbol, delta in row.get('corporate_quantity_deltas', {}).items():
            inventory[symbol] += delta
        for fill in fill_days.get(row['session'], []):
            sign = 1 if fill['side'] == 'buy' else -1
            cash -= sign*money(fill['notional'])+money(fill['commission'])
            inventory[fill['symbol']] += sign*fill['quantity']
        nav = cash+sum((money(marks.loc[row['session'], s])*q for s,q in inventory.items()), Decimal(0))
        if (cash != money(row['cash']) or inventory != row['holdings'] or cash < 0
                or min(inventory.values()) < 0 or not np.isclose(float(nav), row['equity'], rtol=0, atol=1e-8)):
            raise AssertionError('independent portfolio ledger does not reconcile')
    return True
