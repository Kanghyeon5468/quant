"""Event-aware long-only average-cost book. Broker cash is never synthetically credited."""
from decimal import Decimal

import pandas as pd

from quantcore.data.calendar import action_open
from quantcore.strategies.orders import money

ZERO = Decimal(0)


def event_at(event):
    if event.get('effective_at'):
        value = pd.Timestamp(event['effective_at'])
        if value.tzinfo is None:
            raise ValueError('corporate effective time requires UTC offset')
        return value
    return action_open(event['effective_date'])


def event_book(fills, events, cutoff):
    cutoff = pd.Timestamp(cutoff)
    if cutoff.tzinfo is None:
        raise ValueError('book cutoff requires timezone')
    stream, seen = [], set()
    for event in events:
        if event['id'] in seen:
            raise ValueError('duplicate corporate event identity')
        seen.add(event['id'])
        at = event_at(event)
        if at <= cutoff and pd.Timestamp(event['available_at']) <= cutoff:
            stream.append((at, 0, event['id'], 'corporate', event))
    for i, fill in enumerate(fills):
        at = pd.Timestamp(fill['timestamp'])
        if at > cutoff:
            raise ValueError('future fill in corporate book')
        stream.append((at, 1, str(i), 'fill', fill))
    quantity, basis, adjustments, claims, applied, issues = {}, {}, {}, [], [], []
    realized, trade_cash = ZERO, ZERO
    for at, _, _, kind, row in sorted(stream):
        symbol = row['symbol']
        held, cost = quantity.get(symbol, ZERO), basis.get(symbol, ZERO)
        if kind == 'fill':
            qty, price = money(row['qty']), money(row['price'])
            if qty <= 0 or price <= 0 or qty != qty.to_integral_value():
                raise ValueError('invalid whole-share fill')
            if row['side'] == 'buy':
                held, cost = held+qty, cost+qty*price
                trade_cash -= qty*price
            elif row['side'] == 'sell' and held >= qty:
                removed = cost if held == qty else cost*qty/held
                realized += qty*price-removed
                trade_cash += qty*price
                held, cost = held-qty, cost-removed
            else:
                issues.append('sale exceeds event-adjusted owned shares')
            quantity[symbol], basis[symbol] = held, cost
            continue
        state = {'event_id': row['id'], 'symbol': symbol, 'type': row['type'],
                 'effective_at': str(at), 'available_at': row['available_at'], 'status': 'no_exposure'}
        delta = {}
        if row['type'] == 'split' and held:
            ratio = money(row['ratio'])
            if ratio <= 0:
                raise ValueError('positive split ratio required')
            replacement = held*ratio
            delta[symbol] = replacement-held
            quantity[symbol] = replacement
            if replacement != replacement.to_integral_value():
                issues.append('fractional split entitlement requires verified cash-in-lieu reconciliation')
                state['status'] = 'fractional_review'
            else:
                state['status'] = 'book_adjusted'
            state.update(before_qty=str(held), after_qty=str(replacement), preserved_cost_basis=str(cost))
        elif row['type'] == 'rename' and held:
            destination = row.get('new_symbol')
            if not destination:
                issues.append('name/symbol change needs verified destination identity')
                state['status'] = 'identity_review'
            elif destination != symbol:
                if quantity.get(destination, ZERO):
                    issues.append('symbol change collides with existing holdings')
                    state['status'] = 'identity_review'
                else:
                    quantity[destination], basis[destination] = held, cost
                    quantity[symbol], basis[symbol] = ZERO, ZERO
                    delta = {symbol: -held, destination: held}
                    state.update(status='book_adjusted', new_symbol=destination, after_qty=str(held))
        elif row['type'] == 'dividend' and held:
            if row.get('currency', 'USD') != 'USD' or row.get('raw', {}).get('foreign'):
                issues.append('unsupported dividend currency/rights')
                state['status'] = 'currency_review'
            else:
                rate = money(row['rate'])
                if rate < 0:
                    raise ValueError('negative dividend rate')
                claims.append({'event_id': row['id'], 'symbol': symbol, 'ex_at': str(at),
                    'payable_date': row.get('payable_date'), 'eligible_qty': str(held), 'expected_gross': str(held*rate)})
                state.update(status='entitlement_recorded', eligible_qty=str(held), expected_gross=str(held*rate))
        elif row['type'] == 'unsupported' and held:
            issues.append('unsupported corporate action on owned holding')
            state['status'] = 'action_review'
        for target, value in delta.items():
            adjustments[target] = adjustments.get(target, ZERO)+value
        state['quantity_deltas'] = {s: str(v) for s,v in delta.items()}
        applied.append(state)
    return {'inventory': quantity, 'basis': basis, 'realized_gross': realized, 'trade_cash': trade_cash,
            'quantity_adjustments': adjustments, 'corporate_events': applied, 'dividend_claims': claims,
            'issues': sorted(set(issues))}


def dividend_reconciliation(claims, activities, cutoff):
    today = pd.Timestamp(cutoff).tz_convert('America/New_York').date().isoformat()
    groups = {}
    for claim in claims:
        key = claim['symbol'], claim['payable_date']
        group = groups.setdefault(key, {'symbol': key[0], 'payable_date': key[1], 'expected_gross': ZERO, 'event_count': 0})
        group['expected_gross'] += money(claim['expected_gross'])
        group['event_count'] += 1
    result = []
    for (symbol, pay_date), group in groups.items():
        matching = [a for a in activities if a.get('symbol') == symbol and
                    str(a.get('date', ''))[:10] == pay_date and a.get('activity_type') in {'DIV','DIVNRA','DIVFEE','DIVWH','DIVFT','DIVTW'}]
        gross = sum((money(a['net_amount']) for a in matching if a['activity_type'] == 'DIV'), ZERO)
        net = sum((money(a['net_amount']) for a in matching), ZERO)
        status = 'payable_date_unknown' if not pay_date else ('pending_payment' if pay_date > today else
                 ('broker_posted' if abs(gross-group['expected_gross']) <= Decimal('.01') else
                  ('payment_difference' if matching else 'not_credited_in_paper')))
        result.append({**group, 'expected_gross': str(group['expected_gross']), 'broker_gross_received': str(gross),
                       'broker_net_received': str(net), 'status': status, 'cash_credit_created_by_system': '0'})
    return result
