"""One scheduled-session paper rebalance, persistent intent and broker reconciliation."""
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd

from quantcore.data.calendar import sessions
from quantcore.data.providers.alpaca import SYMBOLS, load_snapshot
from quantcore.paper.client import AmbiguousOrder, PaperError, validate_order
from quantcore.paper.corporate import applied_adjustments, share_unit_histories
from quantcore.paper.guard import assess, order_policy
from quantcore.paper.journal import TERMINAL, Journal, check_response, number
from quantcore.paper.policy import MAX_BUDGET
from quantcore.strategies.orders import slot_orders


def own_inventory(context, journal):
    records = journal.records()
    owned = {s: Decimal(0) for s in SYMBOLS}
    known_ids = {r['client_id'] for r in records}
    for record in records:
        r = record['response'] or {}
        owned[record['payload']['symbol']] += (1 if record['payload']['side'] == 'buy' else -1)*number(r.get('filled_qty', 0))
    for symbol, delta in applied_adjustments(journal).items():
        owned[symbol] = owned.get(symbol, Decimal(0))+delta
    actual = {}
    for position in context['positions']:
        symbol, qty = position['symbol'], number(position['qty'])
        if symbol not in SYMBOLS or position.get('side') != 'long' or qty < 0:
            raise PaperError('paper runner requires its own long-only equity positions')
        actual[symbol] = qty
    if any(actual.get(s, Decimal(0)) != owned[s] for s in SYMBOLS):
        raise PaperError('broker position differs from this strategy fill ledger; do not trade unrelated holdings')
    if any(o.get('client_order_id') not in known_ids for o in context['open_orders']):
        raise PaperError('unmanaged paper order exists; no account-wide cancellation or trading')
    return owned


def pending_records(journal):
    return [{**r['payload'], 'remaining_qty': str(number(r['payload']['qty'])-number((r['response'] or {}).get('filled_qty', 0)))}
            for r in journal.records() if r['state'] not in TERMINAL | {'rejected_locally'}]


def cancel_risk_buys(client, journal, risk):
    requests = risk['cancel_pending']
    known = {r['client_id']: r for r in journal.records()}
    for item in requests:
        record = known[item['client_order_id']]
        if record['payload']['side'] != 'buy':
            raise PaperError('risk cancellation is limited to own pending buys')
        client.request('DELETE', '/v2/orders/'+record['response']['id'])
    if requests:
        journal.reconcile(client)
        if any(r['client_id'] in {x['client_order_id'] for x in requests} and r['state'] not in TERMINAL
               for r in journal.records()):
            raise PaperError('risk cancellation not yet confirmed; no new order permitted', retryable=True)
    return [{'symbol': x['symbol'], 'rules': x['rules']} for x in requests]


def monitor_risk(client, directory, snapshot):
    journal = Journal(directory)
    try:
        with journal.lock():
            journal.reconcile(client)
            context = client.context()
            config = journal.configuration()
            if config:
                journal.configure(str(context['account']['id']), config['strategy'], journal.budget())
            owned = own_inventory(context, journal)
            try:
                frame, _, _ = load_snapshot(snapshot)
                histories = {s: frame[frame.symbol == s].sort_values('timestamp') for s in SYMBOLS}
            except (ValueError, OSError):
                histories = {}  # The guard vetoes entries and cancels own pending buys without trusted inputs.
            histories = share_unit_histories(histories, journal, context['clock']['timestamp'])
            risk = assess(journal, context, histories, owned, pending_records(journal), [])
            risk['cancel_actions'] = cancel_risk_buys(client, journal, risk)
            return risk
    finally:
        journal.close()


def make_plan(snapshot, context, journal, strategy='momentum', budget=None):
    budget = number(budget) if budget is not None else journal.budget()
    if strategy not in ('momentum', 'mean_reversion') or not 0 < budget <= MAX_BUDGET:
        raise PaperError('choose an existing strategy and paper budget in (0, $100,000]')
    frame, _, manifest = load_snapshot(snapshot)
    if manifest.get('feed') != 'iex' or manifest.get('source') != 'alpaca-iex-regular-1min':
        raise PaperError('paper signals require the validated actual IEX snapshot')
    clock, account = context['clock'], context['account']
    now = pd.Timestamp(clock['timestamp'])
    if now.tzinfo is None:
        raise PaperError('broker clock has no timezone')
    local_day = now.tz_convert('America/New_York').date()
    complete = sessions(local_day-pd.Timedelta(days=15), local_day, now)
    if complete.empty or manifest['end'] != complete.index[-1]:
        raise PaperError('snapshot is stale or from the future; collect latest completed regular-session data')
    if clock['is_open']:
        execution_day = str(local_day)
        opening = sessions(local_day, local_day).iloc[0]['open']
        if now > opening+pd.Timedelta(minutes=5):
            raise PaperError('missed next-open execution window; no intraday catch-up order')
    else:
        execution_day = str(pd.Timestamp(clock['next_open']).tz_convert('America/New_York').date())
    execution_schedule = sessions(execution_day, execution_day)
    if execution_schedule.empty:
        raise PaperError('broker next session does not match exchange calendar')
    execution_open = execution_schedule.iloc[0]['open']
    if not clock['is_open'] and pd.Timestamp(clock['next_open']) != execution_open:
        raise PaperError('broker next-open time disagrees with exchange calendar')
    raw_actions = json.loads((Path(snapshot)/'actions.json').read_text())
    for kind in ('forward_splits', 'reverse_splits'):
        if any(row['symbol'] in SYMBOLS and manifest['end'] < row['ex_date'] <= execution_day
               for row in raw_actions.get(kind, [])):
            raise PaperError('split before execution requires a refreshed reference price')
    fingerprint = journal.configure(str(account['id']), strategy, budget)
    records = journal.records()
    owned = own_inventory(context, journal)
    pending_orders = pending_records(journal)
    known_ids = {r['client_id'] for r in records}
    ids = {s: f'qcp1-{fingerprint}-{strategy.replace("_", "")}-{execution_day.replace("-", "")}-{s}'
           +(f'-r{journal.revision()}' if journal.revision() else '') for s in SYMBOLS}
    blocked = {o['symbol'] for o in pending_orders} | {s for s in SYMBOLS if ids[s] in known_ids}
    histories = {s: frame[frame.symbol == s].sort_values('timestamp').copy() for s in SYMBOLS}
    if any(len(g) < 60 or g.iloc[-1].session != manifest['end'] or (g.available_at > now).any()
           for g in histories.values()):
        raise PaperError('signal has insufficient history, missing current session or future data')
    histories = share_unit_histories(histories, journal, now)
    allocation = slot_orders(histories, owned, min(number(account['cash']), number(account['buying_power'])),
                             budget, strategy, blocked, pending_orders, order_policy(journal.directory))
    risk = assess(journal, context, histories, owned, pending_orders, allocation['orders'])
    orders = [{**o, 'client_order_id': ids[o['symbol']]} for o in risk['orders']]
    for order in orders:
        validate_order(order)
    decisions = allocation['decisions']
    for item in risk['rejected']:
        next(d for d in decisions if d['symbol'] == item['symbol'])['decision'] = 'risk_restricted'
    buy_cost = sum((number(o['qty'])*number(o['limit_price']) for o in orders if o['side'] == 'buy'), Decimal(0))
    return {'mode': 'paper', 'endpoint': 'https://paper-api.alpaca.markets', 'strategy': strategy,
            'budget_usd': str(budget), 'budget_revision': journal.revision(),
            'max_new_buy_limit_notional_usd': str(buy_cost),
            'snapshot_id': Path(snapshot).name, 'snapshot_hashes': manifest['hashes'],
            'signal_session': manifest['end'], 'execution_session': execution_day,
            'next_open': str(execution_open), 'broker_clock': clock, 'decisions': decisions, 'orders': orders,
            'risk': risk, 'order_policy': allocation['order_policy'],
            'order_policy_version': allocation['order_policy_version'], 'references': allocation['references'],
            'signal_evidence': {s: {'signal_close': float(f.signal_close.iloc[-1]),
                'sma_60': float(f.signal_close.tail(60).mean()), 'reference_close': float(f.close.iloc[-1]),
                'signal_available_at': str(f.available_at.iloc[-1]),
                'target_weight_within_slot': next(d['target_weight_within_slot'] for d in decisions if d['symbol'] == s),
                'risk_rules': [rule for item in risk['rejected'] if item['symbol'] == s for rule in item['rules']]}
                for s, f in histories.items()}}


def execute_plan(client, journal, plan):
    responses = []
    for payload in plan['orders']:
        if (journal.directory/'STOP').exists():
            raise PaperError('local STOP file blocks new paper orders')
        remote = client.by_client_id(payload['client_order_id'])
        if remote is None:
            journal.save(payload, 'submitting')  # Durable intent before any POST.
            try:
                remote = client.request('POST', '/v2/orders', order=payload)
            except AmbiguousOrder:
                remote = client.by_client_id(payload['client_order_id'])
                if remote is None:
                    journal.save(payload, 'unknown')
                    raise AmbiguousOrder('paper POST outcome unknown; stopped without retry') from None
            except PaperError:
                journal.save(payload, 'rejected_locally')
                raise
        check_response(payload, remote)
        journal.save(payload, remote['status'], remote)
        responses.append(remote)
        if remote['status'] in ('rejected', 'suspended', 'stopped'):
            raise PaperError('paper order rejected/stopped; remaining submissions stopped')
    return responses


def run_once(client, directory, snapshot, strategy='momentum', budget=None, submit=False):
    journal = Journal(directory)
    try:
        with journal.lock():
            # Refresh fills before comparing positions; a newly filled order is not an unrelated position.
            journal.reconcile(client)
            context = client.context()
            plan = make_plan(snapshot, context, journal, strategy, budget)
            if submit:
                journal.record_model(plan)
                cancel_risk_buys(client, journal, plan['risk'])
                if plan['risk']['cancel_pending']:
                    plan = make_plan(snapshot, client.context(), journal, strategy, budget)
                for payload in plan['orders']:
                    asset = client.request('GET', '/v2/assets/'+payload['symbol'])
                    if asset.get('status') != 'active' or asset.get('tradable') is not True or asset.get('class') != 'us_equity':
                        raise PaperError('asset is not an active tradable US equity')
                (Path(directory)/'latest_plan.json').write_text(json.dumps(plan, indent=2)+'\n')
                execute_plan(client, journal, plan)
                journal.reconcile(client)
            report = {**plan, 'submitted': submit, 'checked_at': datetime.now(timezone.utc).isoformat(),
                      'journal': journal.records()}
            name = 'latest_run.json' if submit else 'latest_plan.json'
            (Path(directory)/name).write_text(json.dumps(report, indent=2)+'\n')
            return report
    finally:
        journal.close()


def status(client, directory):
    journal = Journal(directory)
    try:
        with journal.lock():
            journal.reconcile(client)
            context = client.context()
            report = {'mode': 'paper', 'checked_at': datetime.now(timezone.utc).isoformat(),
                      'budget_usd': str(journal.budget()), 'budget_revision': journal.revision(),
                      'clock': context['clock'], 'journal': journal.records(),
                      'positions': context['positions'], 'open_orders_count': len(context['open_orders']),
                      'modeled_fill_costs': journal.cost_estimates(),
                      'account_summary': {k: context['account'].get(k) for k in ('cash', 'equity', 'buying_power', 'last_equity')}}
            (Path(directory)/'latest_status.json').write_text(json.dumps(report, indent=2)+'\n')
            return report
    finally:
        journal.close()


def cancel_own(client, directory):
    journal = Journal(directory)
    try:
        with journal.lock():
            journal.reconcile(client)
            for record in journal.records():
                if record['state'] not in TERMINAL | {'rejected_locally'}:
                    client.request('DELETE', '/v2/orders/'+record['response']['id'])
            journal.reconcile(client)
            return journal.records()
    finally:
        journal.close()
