"""Explicit user-authorized paper maintenance/re-entry, separate from daily automation."""

import hashlib
import json
import re
import sqlite3
from decimal import Decimal
from pathlib import Path

import pandas as pd

from quantcore.data.calendar import sessions
from quantcore.data.providers.alpaca import SYMBOLS
from quantcore.data.reference.securities import load_reference
from quantcore.information.store import now
from quantcore.paper.client import PaperError
from quantcore.paper.corporate import verified_book
from quantcore.paper.journal import Journal, number
from quantcore.paper.market import atomic_json
from quantcore.paper.reentry_reference import authorized_reference


def backup(journal, label):
    folder = journal.directory / 'manual_audit'
    folder.mkdir(exist_ok=True)
    path = folder / (pd.Timestamp.now(tz='UTC').strftime('%Y%m%dT%H%M%S%fZ')+'-'+label+'.sqlite3')
    destination = sqlite3.connect(path)
    try:
        journal.db.backup(destination)
    finally:
        destination.close()


def adopt_closures(journal, client, quantities, after, until, reason):
    """Approve only specified, terminal, whole-share sells closing existing strategy inventory."""
    from quantcore.paper.runner import own_inventory

    if not reason.strip() or not quantities or any(s not in SYMBOLS for s in quantities):
        raise PaperError('explicit user authorization and closure quantities are required')
    journal.reconcile(client)
    context = client.context()
    config = journal.configuration()
    if not config:
        raise PaperError('initialize journal before importing manual closures')
    journal.configure(str(context['account']['id']), config['strategy'], journal.budget())
    if context['positions'] or context['open_orders']:
        raise PaperError('manual closure adoption requires a flat account with no open orders')
    records = journal.accounting_records()
    known = {(r['response'] or {}).get('id') for r in records}
    cutoff = pd.Timestamp(context['clock']['timestamp'])
    if not pd.Timestamp(after) < pd.Timestamp(until) <= cutoff:
        raise PaperError('manual closure approval window must be in the past')
    activities = client.activities(after, until)
    unknown = [a for a in activities if a.get('activity_type') == 'FILL' and a.get('order_id') not in known]
    existing = journal.external_records()
    if not unknown:
        own_inventory(context, journal)
        if existing:
            return {'status': 'already_recorded', 'orders': len(existing)}
        raise PaperError('no matching manual fills to approve')
    totals: dict[str, Decimal] = {}
    candidates = []
    for order_id in sorted({a['order_id'] for a in unknown}):
        if not re.fullmatch(r'[0-9a-fA-F-]{36}', order_id):
            raise PaperError('invalid manual order identity')
        remote = client.request('GET', '/v2/orders/'+order_id)
        symbol, qty = remote.get('symbol'), number(remote.get('qty', 'NaN'))
        fills = [a for a in unknown if a['order_id'] == order_id]
        if (remote.get('id') != order_id or remote.get('status') != 'filled' or remote.get('side') != 'sell'
                or symbol not in quantities or remote.get('asset_class') != 'us_equity'
                or qty <= 0 or qty != qty.to_integral_value() or number(remote.get('filled_qty')) != qty
                or number(remote.get('filled_avg_price')) <= 0 or not remote.get('client_order_id')
                or sum((number(a['qty']) for a in fills), number(0)) != qty
                or any(a['symbol'] != symbol or a['side'] != 'sell' or number(a['price']) <= 0
                       or not pd.Timestamp(after) <= pd.Timestamp(a['transaction_time']) <= pd.Timestamp(until) for a in fills)):
            raise PaperError('manual closure order/fills differ from the approved scope')
        totals[symbol] = totals.get(symbol, number(0))+qty
        candidates.append({'client_id': remote['client_order_id'], 'state': 'filled', 'response': remote,
            'origin': 'user_confirmed_manual_closure',
            'payload': {k: remote.get(k) for k in ('symbol','side','qty','type','time_in_force','limit_price','client_order_id')}})
    if totals != {s:number(q) for s,q in quantities.items()}:
        raise PaperError('manual sell totals differ from explicitly approved quantities')
    # Combine historical activities with the new actual fills. Never invent cash, fills or inventory.
    cached = journal.db.execute("SELECT 1 FROM sqlite_master WHERE name='performance_activities'").fetchone()
    history = {a['id']:a for a in activities}
    if cached:
        history.update({json.loads(raw)['id']:json.loads(raw) for raw, in journal.db.execute('SELECT data FROM performance_activities')})
    reference = load_reference(journal.directory.parent.parent)
    book = verified_book(records+candidates, list(history.values()), [], reference['actions'] if reference else [], cutoff)
    if book['issues']:
        raise PaperError('manual closure ledger verification failed: '+', '.join(book['issues']))
    backup(journal, 'before-manual-closure')
    journal.db.execute('CREATE TABLE IF NOT EXISTS approved_external_orders (order_id TEXT PRIMARY KEY, data TEXT, approved_at TEXT, reason TEXT)')
    for row in candidates:
        journal.db.execute('INSERT INTO approved_external_orders VALUES (?,?,?,?)',
            (row['response']['id'], json.dumps(row), now(), reason))
    journal.db.commit()
    own_inventory(context, journal)
    return {'status':'recorded', 'orders':len(candidates), 'quantities':{s:str(q) for s,q in totals.items()},
            'realized_gross':str(book['realized_gross']), 'reason':reason}


def collect_references(data_client, clock):
    stamp = pd.Timestamp(clock['timestamp'])
    day = stamp.tz_convert('America/New_York').date()
    schedule = sessions(day, day)
    if not clock['is_open'] or schedule.empty:
        raise PaperError('manual intraday re-entry requires an open regular session')
    opening, closing = schedule.iloc[0][['open','close']]
    if not opening+pd.Timedelta(minutes=2) <= stamp < closing-pd.Timedelta(minutes=2):
        raise PaperError('manual reference unavailable near session boundary')
    pages = list(data_client.pages('/v2/stocks/bars', {'symbols':','.join(SYMBOLS),
        'start':max(opening, stamp-pd.Timedelta(minutes=10)).isoformat(), 'end':stamp.floor('min').isoformat(),
        'timeframe':'1Min','adjustment':'raw','feed':'iex','limit':1000,'sort':'asc'}))
    references = {}
    for symbol in SYMBOLS:
        bars = [b for p in pages for b in p.get('bars', {}).get(symbol, [])]
        if len({b['t'] for b in bars}) != len(bars):
            raise PaperError('duplicate current-session bars')
        eligible = [b for b in bars if opening <= pd.Timestamp(b['t'])
                    and pd.Timestamp(b['t'])+pd.Timedelta(minutes=2) <= stamp]
        if not eligible:
            raise PaperError('no completed current-session IEX bar for '+symbol)
        bar = max(eligible, key=lambda b:pd.Timestamp(b['t']))
        values = [number(bar[k]) for k in ('o','h','l','c','v')]
        if (min(values) <= 0 or values[2] > min(values[:2]+values[3:4])
                or values[1] < max(values[0],values[2],values[3])):
            raise PaperError('invalid actual minute OHLCV')
        references[symbol] = {'price':str(number(bar['c'])), 'bar_start':bar['t'],
            'bar_end':(pd.Timestamp(bar['t'])+pd.Timedelta(minutes=1)).isoformat()}
    return {'source':'alpaca-iex-regular-1min', 'session':str(day), 'collected_at':now(),
        'bar_availability_delay_minutes_assumed':1, 'references':references,
        'raw_sha256':hashlib.sha256(json.dumps(pages, sort_keys=True).encode()).hexdigest(), 'raw_pages':pages}


def rebalance(root, client, data_client, snapshot, request_id, reason):
    """One durable manual request; retries return its receipt, never submit a second set."""
    from quantcore.paper.corporate import reconcile_corporate
    from quantcore.paper.runner import execute_plan, make_plan, own_inventory, pending_records

    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', request_id) or not reason.strip():
        raise PaperError('a stable user request ID and authorization reason are required')
    root = Path(root)
    directory = root/'artifacts/paper_trading'
    mutex, journal = Journal(directory/'automation'), Journal(directory)
    try:
        with mutex.lock():
            if (directory/'STOP').exists():
                raise PaperError('STOP blocks manual re-entry')
            state_file = directory/'automation/state.json'
            if state_file.exists() and json.loads(state_file.read_text()).get('blocked'):
                raise PaperError('review and resolve the existing automation block before manual re-entry')
            reconcile_corporate(client, root, refresh=False)
            with journal.lock():
                journal.db.execute('CREATE TABLE IF NOT EXISTS manual_rebalances (revision INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT UNIQUE, state TEXT, data TEXT)')
                old = journal.db.execute('SELECT state,data FROM manual_rebalances WHERE request_id=?', (request_id,)).fetchone()
                if old:
                    return {'status':old[0], 'duplicate_request':True, 'request_id':request_id}
                journal.reconcile(client)
                context = client.context()
                own_inventory(context, journal)
                if pending_records(journal):
                    raise PaperError('resolve existing own pending orders before manual re-entry')
                refs = collect_references(data_client, context['clock'])
                refs.update(reason=reason, request_id=request_id, authorized_at=now())
                backup(journal, 'before-manual-reentry')
                journal.db.execute('INSERT INTO manual_rebalances (request_id,state,data) VALUES (?,?,?)',
                    (request_id,'prepared',json.dumps(refs)))
                journal.db.commit()
                context = client.context()
                plan = make_plan(snapshot, context, journal, manual_request_id=request_id)
                # Existing halt/drawdown latches remain enforced by make_plan's shared risk engine.
                if plan['risk']['cancel_pending']:
                    raise PaperError('pending cancellation required; no manual orders submitted')
                for order in plan['orders']:
                    asset = client.request('GET','/v2/assets/'+order['symbol'])
                    if asset.get('status') != 'active' or not asset.get('tradable') or asset.get('class') != 'us_equity':
                        raise PaperError('asset is not an active tradable US equity')
                # Recheck observed price age/account immediately before persistent intent + POST.
                fresh = client.context()
                authorized_reference(journal, request_id, pd.Timestamp(fresh['clock']['timestamp']), fresh['clock']['is_open'])
                if any(fresh[k] != context[k] for k in ('positions','open_orders')) or number(fresh['account']['cash']) < number(plan['max_new_buy_limit_notional_usd']):
                    raise PaperError('account changed during manual planning; no new order')
                folder = directory/'manual_audit'/request_id
                folder.mkdir(parents=True, exist_ok=True)
                atomic_json(folder/'source.json',refs)
                atomic_json(folder/'plan.json',plan)
                journal.record_model(plan)
                journal.db.execute('UPDATE manual_rebalances SET state=? WHERE request_id=?',('submitting',request_id))
                journal.db.commit()
                execute_plan(client, journal, plan)
                journal.reconcile(client)
                journal.db.execute('UPDATE manual_rebalances SET state=? WHERE request_id=?',('submitted',request_id))
                journal.db.commit()
                report = {**plan,'submitted':True,'checked_at':now(),'journal':journal.records()}
                atomic_json(folder/'receipt.json',report)
                atomic_json(directory/'latest_run.json',report)
                return report
    finally:
        journal.close()
        mutex.close()
