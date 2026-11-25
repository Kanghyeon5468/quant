"""Persistent risk tracking and local alerts; broker operations remain in the runner."""
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

from quantcore.data.calendar import sessions
from quantcore.paper.corporate import risk_classification
from quantcore.paper.market import atomic_json
from quantcore.risk.limits import RiskLimits, account_state, features, filter_orders
from quantcore.strategies.orders import OrderPolicy


def settings(directory, name, model):
    local = Path(directory)/name
    configured = Path(__file__).resolve().parents[2]/'configs'/name
    path = local if local.exists() else configured
    return model.model_validate_json(path.read_text()) if path.exists() else model()


def order_policy(directory):
    return settings(directory, 'order_policy.json', OrderPolicy)


def assess(journal, context, histories, inventory, pending, orders):
    try:
        return _assess(journal, context, histories, inventory, pending, orders)
    except (ValueError, KeyError, TypeError) as error:
        result = {'mode': 'paper', 'checked_at': str(context['clock']['timestamp']), 'status': 'halted',
            'data_status': 'unavailable', 'reason': str(error), 'halt_rules': ['risk_data_unavailable'],
            'orders': [o for o in orders if o['side'] == 'sell'], 'rejected': [],
            'cancel_pending': [{'client_order_id': o['client_order_id'], 'symbol': o['symbol'],
                                'rules': ['risk_data_unavailable']} for o in pending if o['side'] == 'buy'],
            'alerts': [{'rule': 'risk_data_unavailable', 'severity': 'critical', 'symbol': 'PORTFOLIO'}]}
        atomic_json(journal.directory/'risk_status.json', result)
        public = {k: v for k, v in result.items() if k not in ('orders', 'cancel_pending')}
        atomic_json(journal.directory.parent/'paper_risk_public'/'status.json', public)
        return result


def _assess(journal, context, histories, inventory, pending, orders):
    limits = settings(journal.directory, 'risk_limits.json', RiskLimits)
    clock = pd.Timestamp(context['clock']['timestamp'])
    limits, classification = risk_classification(limits, journal.directory.parent.parent, clock.isoformat())
    day = str(clock.tz_convert('America/New_York').date())
    account = context['account']
    identity = hashlib.sha256(str(account['id']).encode()).hexdigest()
    journal.db.execute('CREATE TABLE IF NOT EXISTS risk_state (id INTEGER PRIMARY KEY, data TEXT NOT NULL)')
    journal.db.execute('''CREATE TABLE IF NOT EXISTS risk_alerts (
        id TEXT PRIMARY KEY, first_seen TEXT, last_seen TEXT, count INTEGER, data TEXT)''')
    row = journal.db.execute('SELECT data FROM risk_state WHERE id=1').fetchone()
    state = json.loads(row[0]) if row else {}
    equity = float(account.get('equity', 'nan'))
    last_equity = float(account.get('last_equity', 'nan'))
    budget = float(journal.budget())
    state = account_state(state, equity, last_equity, budget, day, identity)
    nav, peak, daily_start = state['last_equity'], state['peak'], state['daily_start']
    daily_latched = state['daily_latched']
    try:
        if nav <= 0 or daily_start <= 0:
            raise ValueError('nonpositive strategy NAV')
        local_day = clock.tz_convert('America/New_York').date()
        expected = sessions(local_day-pd.Timedelta(days=15), local_day, clock-pd.Timedelta(minutes=10))
        if any(str(f.session.iloc[-1]) != expected.index[-1] for f in histories.values()):
            raise ValueError('risk history is stale outside close collection grace')
        feature = features(histories, clock)
        marks = dict(feature['prices'])
        for position in context['positions']:
            price = float(position.get('current_price', marks[position['symbol']]))
            if not math.isfinite(price) or price <= 0:
                raise ValueError('invalid broker position mark')
            marks[position['symbol']] = price
        result = filter_orders(feature, inventory, marks, pending, orders, nav, daily_start, peak,
                               limits, daily_latched, state.get('drawdown_latched', False))
        result.update(classification=classification, data_status='ok', features_as_of=max(str(f.available_at.iloc[-1]) for f in histories.values()))
    except (ValueError, KeyError, IndexError) as error:
        result = {'orders': [o for o in orders if o['side'] == 'sell'],
                  'rejected': [{'symbol': o['symbol'], 'requested_qty': int(o['qty']), 'approved_qty': 0,
                                'rules': ['risk_data_unavailable']} for o in orders if o['side'] == 'buy'],
                  'cancel_pending': [{'client_order_id': o['client_order_id'], 'symbol': o['symbol'],
                                      'rules': ['risk_data_unavailable']} for o in pending if o['side'] == 'buy'],
                  'halt_rules': ['risk_data_unavailable'], 'current_violations': [], 'data_status': 'unavailable',
                  'reason': str(error), 'limits': limits.model_dump(), 'risk_policy_version': limits.version}
    state.update(daily_latched=daily_latched or 'daily_loss' in result['halt_rules'],
                 drawdown_latched=state.get('drawdown_latched', False) or 'drawdown' in result['halt_rules'])
    journal.db.execute('INSERT INTO risk_state VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',
                       (json.dumps(state, sort_keys=True),))
    alerts = [{'rule': rule, 'severity': 'critical', 'symbol': 'PORTFOLIO'}
              for rule in result['halt_rules']+result['current_violations']]
    for item in result['rejected']+result['cancel_pending']:
        alerts += [{'rule': rule, 'severity': 'warning', 'symbol': item['symbol']} for rule in item['rules']]
    if result.get('sector_unclassified'):
        alerts.append({'rule': 'sector_unclassified', 'severity': 'info', 'symbol': 'PORTFOLIO'})
    for alert in alerts:
        key = hashlib.sha256(json.dumps([day, limits.version, alert], sort_keys=True).encode()).hexdigest()
        journal.db.execute('''INSERT INTO risk_alerts VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(id) DO UPDATE SET last_seen=excluded.last_seen, count=count+1''',
            (key, clock.isoformat(), clock.isoformat(), json.dumps(alert)))
    journal.db.commit()
    events = [dict(json.loads(raw), first_seen=first, last_seen=last, observations=count)
              for first, last, count, raw in journal.db.execute(
                  'SELECT first_seen,last_seen,count,data FROM risk_alerts ORDER BY last_seen DESC LIMIT 30')]
    report = {**result, 'mode': 'paper', 'checked_at': clock.isoformat(), 'strategy_nav': nav,
              'broker_equity': equity, 'daily_start': daily_start, 'peak': peak, 'budget_usd': budget,
              'alerts': events, 'daily_latched': state['daily_latched'], 'drawdown_latched': state['drawdown_latched'],
              'status': 'halted' if result['halt_rules'] else ('restricted' if result['rejected'] or result['cancel_pending'] or result['current_violations'] else 'ok')}
    atomic_json(journal.directory/'risk_status.json', report)
    public = {k: v for k, v in report.items() if k not in ('orders', 'cancel_pending')}
    public['pending_cancellations'] = [{'symbol': x['symbol'], 'rules': x['rules']} for x in report['cancel_pending']]
    atomic_json(journal.directory.parent/'paper_risk_public'/'status.json', public)
    return report


def reset_drawdown(journal, reason):
    """Explicit, audited operator reset; resume by itself never clears a risk latch."""
    if not reason.strip() or not (journal.directory/'STOP').exists():
        raise ValueError('pause automation and supply a nonempty reset reason first')
    row = journal.db.execute('SELECT data FROM risk_state WHERE id=1').fetchone()
    if not row:
        raise ValueError('risk has not been initialized')
    state = json.loads(row[0])
    previous = dict(state)
    state.update(peak=state['last_equity'], drawdown_latched=False)
    journal.db.execute('CREATE TABLE IF NOT EXISTS risk_resets (at TEXT, reason TEXT, previous TEXT)')
    journal.db.execute('INSERT INTO risk_resets VALUES (?, ?, ?)',
        (pd.Timestamp.now(tz='UTC').isoformat(), reason.strip(), json.dumps(previous)))
    journal.db.execute('UPDATE risk_state SET data=? WHERE id=1', (json.dumps(state),))
    journal.db.commit()
    return {'drawdown_latched': False, 'daily_latched': state['daily_latched'], 'peak': state['peak']}
