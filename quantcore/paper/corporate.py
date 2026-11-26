"""Corporate-event reconciliation before broker ownership validation. No synthetic fills/cash."""
import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pandas as pd

from quantcore.accounting.corporate import dividend_reconciliation, event_at, event_book
from quantcore.data.reference.securities import classification_asof, collect_reference, load_reference
from quantcore.paper.client import PaperError
from quantcore.paper.journal import TERMINAL, Journal
from quantcore.paper.market import atomic_json


def risk_classification(limits, root, cutoff):
    groups, report = classification_asof(root, str(cutoff))
    # Explicit local assignments remain visible overrides; defaults obtain sourced current groups.
    assignments = {**groups, **limits.sectors}
    return limits.model_copy(update={'sectors': assignments}), report


def applied_adjustments(journal):
    exists = journal.db.execute('SELECT 1 FROM sqlite_master WHERE name="corporate_adjustments"').fetchone()
    result = {}
    if exists:
        for raw, in journal.db.execute('SELECT data FROM corporate_adjustments'):
            for symbol, qty in json.loads(raw)['quantity_deltas'].items():
                result[symbol] = result.get(symbol, Decimal(0))+Decimal(qty)
    return result


def verified_book(records, activities, positions, events, cutoff):
    remote = {(r['response'] or {}).get('id'): r for r in records if (r['response'] or {}).get('id')}
    quantities, fills, issues, unknown = {}, [], [], 0
    for activity in activities:
        if activity.get('activity_type') != 'FILL':
            continue
        record = remote.get(activity.get('order_id'))
        if not record:
            unknown += 1
            continue
        if activity.get('side') != record['payload']['side'] or activity.get('symbol') != record['payload']['symbol']:
            raise ValueError('fill differs from corporate book order identity')
        qty = Decimal(str(activity['qty']))
        quantities[record['client_id']] = quantities.get(record['client_id'], Decimal(0))+qty
        fills.append({'client_id': record['client_id'], 'symbol': activity['symbol'], 'side': activity['side'],
                      'qty': qty, 'price': Decimal(str(activity['price'])), 'timestamp': activity['transaction_time']})
    for r in records:
        if Decimal(str((r['response'] or {}).get('filled_qty', 0))) != quantities.get(r['client_id'], Decimal(0)):
            issues.append('activity quantities and order reconciliation differ')
    book = event_book(fills, events, cutoff)
    position_map = {p['symbol']: p for p in positions}
    for s in set(book['inventory']) | set(position_map):
        if book['inventory'].get(s, Decimal(0)) != Decimal(str(position_map.get(s, {}).get('qty', 0))):
            issues.append('event-adjusted shares do not match broker positions')
    if unknown:
        issues.append('unmanaged fills cannot be attributed')
    book.update(fills=sorted(fills, key=lambda f: pd.Timestamp(f['timestamp'])), unknown_fills=unknown,
                issues=sorted(set(book['issues']+issues)))
    return book


def reconcile_corporate(client, root, *, refresh=True, env_file=None):
    root = Path(root)
    if refresh and (root/'configs/security_master.json').exists():
        # Missing SEC configuration in a keyless test/demo never triggers external requests.
        import os

        from dotenv import dotenv_values
        if load_reference(root) or os.getenv('SEC_USER_AGENT') or dotenv_values(root/'.env').get('SEC_USER_AGENT'):
            collect_reference(root, env_file, client)
    reference = load_reference(root)
    if not reference:
        return {'status': 'unavailable', 'reason': 'corporate reference cache missing'}
    journal = Journal(root/'artifacts/paper_trading')
    try:
        with journal.lock():
            # Orders can fill after the preceding tick. Refresh their quantities before
            # comparing FILL activities, otherwise a stale zero-fill record halts forever.
            journal.reconcile(client)
            context = client.context()
            cutoff = pd.Timestamp(context['clock']['timestamp'])
            config = journal.configuration()
            if config and hashlib.sha256(str(context['account']['id']).encode()).hexdigest() != config['account_hash']:
                raise PaperError('corporate book account identity mismatch')
            records = journal.accounting_records()
            dates = [(r['response'] or {}).get('created_at') or (r['response'] or {}).get('submitted_at') for r in records]
            dates = [pd.Timestamp(d) for d in dates if d]
            start = min(dates+[cutoff-pd.Timedelta(days=7)])-pd.Timedelta(days=1)
            activities = client.activities(start.isoformat(), cutoff.isoformat())
            journal.db.execute('CREATE TABLE IF NOT EXISTS performance_activities (id TEXT PRIMARY KEY, data TEXT)')
            for activity in activities:
                journal.db.execute('INSERT INTO performance_activities VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',
                                   (activity['id'], json.dumps(activity)))
            # Retain earlier fills as the strategy runs longer than the API overlap window.
            activities = [json.loads(r[0]) for r in journal.db.execute('SELECT data FROM performance_activities')]
            events = [e for e in reference['actions'] if e.get('effective_date')]
            book = verified_book(records, activities, context['positions'], events, cutoff)
            renamed = [e for e in book['corporate_events'] if e['type'] == 'rename' and e['status'] == 'book_adjusted']
            unresolved = list(book['issues'])
            if renamed:
                unresolved.append('symbol change reconciled; market universe/identity migration required before trading')
            cancel = []
            for event in events:
                at = event_at(event)
                if event['type'] not in ('split', 'rename') or pd.Timestamp(event['available_at']) > cutoff:
                    continue
                for record in records:
                    submitted = (record['response'] or {}).get('submitted_at') or (record['response'] or {}).get('created_at')
                    if (record['state'] not in TERMINAL | {'rejected_locally'} and record['payload']['symbol'] == event['symbol']
                            and submitted and pd.Timestamp(submitted) < at <= pd.Timestamp(context['clock']['next_open'])):
                        cancel.append(record)
            # Cancel only individually identified own orders before a split/symbol change; require final confirmation.
            for record in {r['client_id']: r for r in cancel}.values():
                client.request('DELETE', '/v2/orders/'+record['response']['id'])
            if cancel:
                journal.reconcile(client)
                ids = {r['client_id'] for r in cancel}
                if any(r['client_id'] in ids and r['state'] not in TERMINAL for r in journal.records()):
                    unresolved.append('corporate order cancellation not confirmed')
            journal.db.execute('CREATE TABLE IF NOT EXISTS corporate_adjustments (event_id TEXT PRIMARY KEY, data TEXT)')
            if not book['issues']:
                for event in book['corporate_events']:
                    if event['quantity_deltas']:
                        previous = journal.db.execute('SELECT data FROM corporate_adjustments WHERE event_id=?', (event['event_id'],)).fetchone()
                        if previous and json.loads(previous[0])['quantity_deltas'] != event['quantity_deltas']:
                            unresolved.append('corporate event revision changes an applied adjustment')
                            continue
                        journal.db.execute('INSERT OR IGNORE INTO corporate_adjustments VALUES (?, ?)', (event['event_id'], json.dumps(event)))
            journal.db.commit()
            classifications, meta = classification_asof(root, cutoff.isoformat())
            public = {'status': 'review_required' if unresolved else 'reconciled', 'checked_at': cutoff.isoformat(),
                'classification': meta, 'risk_groups': classifications, 'official_event_count': len(events),
                'event_counts': {kind:sum(e['type']==kind for e in events) for kind in ['split','dividend','rename','unsupported']},
                'owned_events': [e for e in book['corporate_events'] if e['status'] != 'no_exposure'],
                'dividends': dividend_reconciliation(book['dividend_claims'], activities, cutoff),
                'pending_orders_canceled': len({r['client_id'] for r in cancel}), 'issues': sorted(set(unresolved)),
                'quantity_adjustments': {s:str(v) for s,v in book['quantity_adjustments'].items()},
                'broker_positions_reconciled': not book['issues'], 'cash_credit_created_by_system': 0,
                'last_reference_collection': reference['manifest']['collected_at']}
            atomic_json(root/'artifacts/corporate_public/status.json', public)
            if unresolved:
                transient = set(unresolved) <= {'activity quantities and order reconciliation differ',
                    'event-adjusted shares do not match broker positions'}
                raise PaperError('corporate action requires review: '+unresolved[0], retryable=transient)
            return public
    finally:
        journal.close()


def share_unit_histories(histories, journal, cutoff):
    """Express preceding volume in current share units for ADV/cost limits after a split."""
    exists = journal.db.execute('SELECT 1 FROM sqlite_master WHERE name="corporate_adjustments"').fetchone()
    applied = [json.loads(raw) for raw, in journal.db.execute('SELECT data FROM corporate_adjustments')] if exists else []
    result = {}
    for symbol, original in histories.items():
        frame = original.copy()
        frame = frame[frame.available_at <= pd.Timestamp(cutoff)]
        if frame.empty:
            result[symbol] = frame
            continue
        factors = frame.signal_close/frame.close
        current = float(factors.iloc[-1])
        latest = pd.Timestamp(frame.timestamp.iloc[-1])
        for event in applied:
            if (event['symbol'] == symbol and event['type'] == 'split' and
                    latest < pd.Timestamp(event['effective_at']) <= pd.Timestamp(cutoff)):
                current *= float(Decimal(event['after_qty'])/Decimal(event['before_qty']))
        frame['volume'] = frame.volume*current/factors
        result[symbol] = frame
    return result
