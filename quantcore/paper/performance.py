"""GET-only paper observations and execution attribution, isolated from trading decisions."""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from quantcore.data.reference.securities import load_reference
from quantcore.paper.client import PaperError
from quantcore.paper.corporate import verified_book
from quantcore.paper.journal import Journal, number
from quantcore.paper.market import atomic_json
from quantcore.strategies.orders import OrderPolicy, modeled_cost

ZERO = Decimal(0)


def stamp(value):
    result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('performance timestamps require UTC offsets')
    return result.astimezone(timezone.utc)


def table_map(db, name):
    if name not in {'order_evidence', 'order_models'}:
        raise ValueError('unsupported evidence table')
    exists = db.execute('SELECT 1 FROM sqlite_master WHERE type="table" AND name=?', (name,)).fetchone()
    return {key: json.loads(raw) for key, raw in db.execute(f'SELECT client_id,data FROM {name}')} if exists else {}


def history_rows(payload, now):
    keys = ('timestamp', 'equity', 'profit_loss', 'profit_loss_pct')
    arrays = [payload[k] for k in keys]
    if any(not isinstance(a, list) for a in arrays) or len({len(a) for a in arrays}) != 1:
        raise ValueError('unaligned portfolio history arrays')
    result, seen = [], set()
    for epoch, equity, pnl, ret in zip(*arrays):
        at = datetime.fromtimestamp(float(epoch), timezone.utc)
        if at > now or epoch in seen:
            raise ValueError('future or duplicate portfolio history point')
        seen.add(epoch)
        eq = number(equity)
        if eq < 0:
            raise ValueError('negative account equity')
        if eq == 0:
            continue  # Unfunded intervals are not zero-NAV trading observations.
        day = at.astimezone(ZoneInfo('America/New_York')).date().isoformat()
        result.append({'timestamp': at.isoformat(), 'session': day, 'equity': float(eq),
            'broker_profit_loss': float(number(pnl)) if pnl is not None else None,
            'broker_return': float(number(ret)) if ret is not None else None})
    return sorted(result, key=lambda r: r['timestamp'])


def own_fill_ledger(records, activities, positions, corporate_events=(), cutoff=None):
    """Same event book as pretrade reconciliation; legacy callers retain their exact fill behavior."""
    cutoff = cutoff or datetime.now(timezone.utc)+timedelta(days=36500)
    book = verified_book(records, activities, positions, corporate_events, cutoff)
    issues = list(book['issues'])
    unrealized = ZERO
    positions_by_symbol = {p['symbol']: p for p in positions}
    for symbol, qty in book['inventory'].items():
        position = positions_by_symbol.get(symbol, {})
        if qty and not position.get('current_price'):
            issues.append('broker mark is unavailable')
        elif qty:
            price = number(position['current_price'])
            if price <= 0:
                raise ValueError('positive broker position mark required')
            unrealized += qty*price-book['basis'][symbol]
    return {'status': 'reconciled' if not issues else 'incomplete', 'issues': sorted(set(issues)),
        'realized_gross': float(book['realized_gross']) if not issues else None,
        'unrealized_gross': float(unrealized) if not issues else None, 'fills': book['fills'],
        'unknown_fills': book['unknown_fills'], 'inventory': book['inventory'],
        'corporate_event_count': sum(e['status']!='no_exposure' for e in book['corporate_events'])}


def execution_rows(records, ledger, models, evidence):
    result = []
    for record in records:
        order, remote = record['payload'], record['response'] or {}
        cid, symbol = record['client_id'], order['symbol']
        own = [f for f in ledger['fills'] if f['client_id'] == cid]
        qty = sum((f['qty'] for f in own), ZERO)
        broker_filled = number(remote.get('filled_qty', 0))
        average = sum((f['qty']*f['price'] for f in own), ZERO)/qty if qty and qty == broker_filled else None
        submitted = remote.get('submitted_at') or remote.get('created_at')
        latency = (stamp(own[0]['timestamp'])-stamp(submitted)).total_seconds() if own and submitted else None
        source = models.get(cid, {})
        ref = source.get('reference_close')
        cost, expected, change, gap = None, None, None, None
        if ref and source.get('average_volume_20'):
            policy = OrderPolicy.model_validate(source['policy'])
            cost = modeled_cost(ref, int(order['qty']), source['average_volume_20'], policy)
            sign = 1 if order['side'] == 'buy' else -1
            expected = float(number(ref)*(1+sign*number(cost['adverse_bps'])/10000))
            if average:
                change = sign*(float(average)/float(ref)-1)*10000
                gap = sign*(float(average)-expected)*float(qty)
        ev = evidence.get(cid, {})
        safe_evidence = {k: ev[k] for k in ('strategy', 'signal_close', 'sma_60', 'reference_close',
            'signal_available_at', 'target_weight_within_slot', 'risk_rules', 'captured_at', 'evidence_status',
            'risk_policy_version', 'order_policy_version', 'snapshot_id') if k in ev}
        revision = int(cid.rsplit('-r', 1)[1]) if re.search(r'-r\d+$', cid) else 0
        broker_filled = number(remote.get('filled_qty', 0))
        fraction = broker_filled/number(order['qty'])
        result.append({'key': hashlib.sha256(cid.encode()).hexdigest()[:12], 'symbol': symbol,
            'side': order['side'], 'qty': int(order['qty']), 'filled_qty': int(broker_filled),
            'status': record['state'], 'budget_revision': revision, 'limit_price': float(number(order['limit_price'])),
            'submitted_at': stamp(submitted).isoformat() if submitted else None,
            'first_fill_at': own[0]['timestamp'] if own else None,
            'last_fill_at': own[-1]['timestamp'] if own else None,
            'fill_average_price': float(average) if average else None,
            'first_fill_delay_seconds': latency if latency is not None and latency >= 0 else None,
            'reference_close': ref, 'reference_change_bps': change, 'modeled_reference_price': expected,
            'actual_vs_model_usd': gap,
            'modeled_cost_estimate': float(number(cost['modeled_total_cost'])*fraction) if cost else None,
            'evidence': safe_evidence, 'evidence_status': ev.get('evidence_status', 'unavailable')})
    return result


def execution_metrics(rows):
    submitted = [r for r in rows if r['status'] not in ('rejected_locally', 'submitting', 'unknown')]
    qty = sum(r['qty'] for r in submitted)
    filled = sum(r['filled_qty'] for r in submitted)
    comparable = [r for r in submitted if r['filled_qty'] and r['reference_change_bps'] is not None]
    weight = sum(r['filled_qty'] for r in comparable)
    return {'orders': len(submitted), 'requested_shares': qty, 'filled_shares': filled,
            'filled_orders': sum(r['filled_qty'] == r['qty'] for r in submitted),
            'partial_orders': sum(0 < r['filled_qty'] < r['qty'] for r in submitted),
            'share_fill_rate': filled/qty if qty else None,
            'order_fill_rate': sum(r['filled_qty'] == r['qty'] for r in submitted)/len(submitted) if submitted else None,
            'reference_change_bps': sum(r['reference_change_bps']*r['filled_qty'] for r in comparable)/weight if weight else None,
            'modeled_cost_estimate': sum(r['modeled_cost_estimate'] or 0 for r in submitted),
            'cost_estimate_missing_orders': sum(r['filled_qty'] > 0 and r['modeled_cost_estimate'] is None for r in submitted)}


def compare_backtest(history, root, since):
    path = Path(root)/'docs/portfolio_backtest_results.json'
    unavailable = {'status': 'unavailable', 'reason': '동일 기간의 완료 일별 자료가 아직 없습니다.'}
    if not path.exists():
        return unavailable
    data = json.loads(path.read_text())
    curve = data['results']['momentum_risk_net']['curve']
    daily = {r['session']: r['equity'] for r in history if r['session'] >= since}
    common = [r for r in curve if r['session'] in daily]
    if len(common) < 2:
        return unavailable
    first = common[0]
    points = [{'session': r['session'], 'paper_index': daily[r['session']]/daily[first['session']]*100,
               'backtest_index': r['equity']/first['equity']*100} for r in common]
    return {'status': 'available', 'points': points,
            'basis': '같은 날짜의 계좌 평가액을 100으로 환산; 초기 보유·체결·입출금 조건은 다를 수 있습니다.'}


def _collect(client, root, journal):
    db = journal.db
    for sql in [
        'CREATE TABLE IF NOT EXISTS performance_meta (id INTEGER PRIMARY KEY, data TEXT)',
        'CREATE TABLE IF NOT EXISTS performance_fetches (source TEXT, hash TEXT, at TEXT, data TEXT, PRIMARY KEY(source,hash))',
        'CREATE TABLE IF NOT EXISTS performance_activities (id TEXT PRIMARY KEY, data TEXT)',
        'CREATE TABLE IF NOT EXISTS performance_history (at TEXT PRIMARY KEY, data TEXT)',
        'CREATE TABLE IF NOT EXISTS performance_observations (bucket TEXT PRIMARY KEY, data TEXT)']:
        db.execute(sql)
    account = client.request('GET', '/v2/account')
    clock = client.request('GET', '/v2/clock')
    positions = client.request('GET', '/v2/positions')
    now = stamp(clock['timestamp'])
    identity = hashlib.sha256(str(account['id']).encode()).hexdigest()
    config = journal.configuration() or {}
    if config.get('account_hash', identity) != identity:
        raise ValueError('performance account differs from strategy journal')
    if account.get('currency') != 'USD':
        raise ValueError('paper performance requires USD account')
    equity, cash, last = number(account['equity']), number(account['cash']), number(account['last_equity'])
    if equity <= 0 or last <= 0:
        raise ValueError('nonpositive broker account equity')
    old = db.execute('SELECT data FROM performance_meta WHERE id=1').fetchone()
    meta = json.loads(old[0]) if old else {'account_hash': identity, 'started_at': now.isoformat(), 'initial_equity': str(equity)}
    if meta['account_hash'] != identity:
        raise ValueError('performance store account changed')
    records = journal.records()
    errors, sections = [], {}
    try:
        payload = client.portfolio_history((now-timedelta(days=90)).isoformat(), now.isoformat())
        rows = history_rows(payload, now)
        raw = json.dumps(payload, sort_keys=True)
        db.execute('INSERT OR IGNORE INTO performance_fetches VALUES (?, ?, ?, ?)',
            ('history', hashlib.sha256(raw.encode()).hexdigest(), now.isoformat(), raw))
        db.execute('DELETE FROM performance_history WHERE at>=? AND at<=?',
            ((now-timedelta(days=90)).isoformat(), now.isoformat()))
        for row in rows:
            db.execute('INSERT INTO performance_history VALUES (?, ?) ON CONFLICT(at) DO UPDATE SET data=excluded.data',
                       (row['timestamp'], json.dumps(row)))
        meta['history_checked_at'] = now.isoformat()
        meta['history_base_value'] = float(number(payload['base_value'])) if payload.get('base_value') is not None else None
        meta['history_base_value_asof'] = payload.get('base_value_asof')
        meta['unfunded_points_excluded'] = len(payload['timestamp'])-len(rows)
        sections['history'] = 'ok'
    except (PaperError, ValueError, KeyError, TypeError, OverflowError) as error:
        sections['history'] = 'unavailable'
        errors.append({'source': 'history', 'error': type(error).__name__})
    try:
        if meta.get('activities_checked_at'):
            after = stamp(meta['activities_checked_at'])-timedelta(days=7)
        else:
            dates = [stamp((r['response'] or {}).get('created_at') or (r['response'] or {}).get('submitted_at'))
                     for r in records if (r['response'] or {}).get('created_at') or (r['response'] or {}).get('submitted_at')]
            encoded = [datetime.strptime(m.group(1), '%Y%m%d').replace(tzinfo=timezone.utc)-timedelta(days=7)
                       for r in records if (m := re.search(r'-(\d{8})-[A-Z]+', r['client_id']))]
            after = min(dates+encoded+[now-timedelta(days=7)])
        activities = client.activities(after.isoformat(), now.isoformat())
        for row in activities:
            if row.get('activity_type') == 'FILL' and stamp(row['transaction_time']) > now:
                raise ValueError('future fill activity')
        raw = json.dumps(activities, sort_keys=True)
        db.execute('INSERT OR IGNORE INTO performance_fetches VALUES (?, ?, ?, ?)',
            ('activities', hashlib.sha256(raw.encode()).hexdigest(), now.isoformat(), raw))
        for row in activities:
            db.execute('INSERT INTO performance_activities VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',
                       (row['id'], json.dumps(row)))
        meta['activities_checked_at'] = now.isoformat()
        sections['activities'] = 'ok'
    except (PaperError, ValueError, KeyError, TypeError) as error:
        sections['activities'] = 'unavailable'
        errors.append({'source': 'activities', 'error': type(error).__name__})
    observation = {'timestamp': now.isoformat(), 'equity': float(equity), 'cash': float(cash),
                   'daily_equity_change': float(equity-last), 'daily_equity_change_pct': float(equity/last-1)}
    bucket = now.replace(minute=now.minute//5*5, second=0, microsecond=0).isoformat()
    db.execute('INSERT INTO performance_observations VALUES (?, ?) ON CONFLICT(bucket) DO UPDATE SET data=excluded.data',
               (bucket, json.dumps(observation)))
    db.execute('INSERT INTO performance_meta VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',
               (json.dumps(meta),))
    db.commit()
    stored = [json.loads(r[0]) for r in db.execute('SELECT data FROM performance_activities')]
    reference = load_reference(root)
    corporate_events = reference['actions'] if reference else []
    ledger = own_fill_ledger(records, stored, positions, corporate_events, now.isoformat())
    if sections['activities'] != 'ok':
        ledger.update(status='incomplete', realized_gross=None, unrealized_gross=None)
    non_trade = [a for a in stored if a.get('activity_type') != 'FILL']
    cash_types = {'CSD', 'CSW', 'ACATC', 'JNLC'}
    cash_only = cash_types | {'DIV', 'DIVFEE', 'DIVNRA', 'INT', 'INTNRA', 'INTTW', 'FEE', 'PTC', 'PTR', 'CFEE', 'CGD'}
    matched_types = {'SSP','SPLIT','SC','NC'} if ledger['status']=='reconciled' and ledger['corporate_event_count'] else set()
    unknown_actions = [a for a in non_trade if a.get('activity_type') not in cash_only | matched_types]
    if unknown_actions:
        ledger.update(status='review_required', realized_gross=None, unrealized_gross=None)
        ledger['issues'].append('corporate action or unsupported activity requires review')
    flows = [a for a in non_trade if a.get('activity_type') in cash_types and
             (not a.get('created_at') or stamp(a['created_at']) >= stamp(meta['started_at']))]
    rows = execution_rows(records, ledger, table_map(db, 'order_models'), table_map(db, 'order_evidence'))
    daily = [json.loads(r[0]) for r in db.execute('SELECT data FROM performance_history ORDER BY at')]
    observations = [json.loads(r[0]) for r in db.execute(
        'SELECT data FROM (SELECT bucket,data FROM performance_observations ORDER BY bucket DESC LIMIT 2000) ORDER BY bucket')]
    # Comparison uses only completed regular sessions, not an evolving current-day account mark.
    from quantcore.data.calendar import sessions
    complete = sessions((now-timedelta(days=90)).date(), now.date(), now)
    completed = [r for r in daily if r['session'] in set(complete.index)]
    since = stamp(meta['started_at']).astimezone(ZoneInfo('America/New_York')).date().isoformat()
    comparison = compare_backtest(completed, root, since) if not flows and not unknown_actions and sections['history'] == 'ok' and sections['activities'] == 'ok' and ledger['status'] == 'reconciled' else {'status': 'unavailable', 'reason': '계좌 활동 검토가 필요합니다.'}
    safe_positions = [{k: p.get(k) for k in ('symbol', 'qty', 'avg_entry_price', 'current_price', 'market_value', 'unrealized_pl', 'unrealized_plpc')} for p in positions]
    decisions = db.execute('SELECT data FROM decision_runs ORDER BY session DESC LIMIT 1').fetchone() if db.execute(
        'SELECT 1 FROM sqlite_master WHERE type="table" AND name="decision_runs"').fetchone() else None
    from quantcore.paper.reports import read_corporate
    return {'corporate_actions': read_corporate(Path(root)/'artifacts/corporate_public'),
        'mode': 'paper', 'currency': 'USD', 'status': 'ok' if not errors and ledger['status'] == 'reconciled' else 'degraded',
        'checked_at': datetime.now(timezone.utc).isoformat(), 'broker_observed_at': now.isoformat(),
        'collection_errors': errors, 'sections': sections,
        'source': 'Alpaca paper account / portfolio history / FILL activities + own journal',
        'tracking_started_at': meta['started_at'], 'history_checked_at': meta.get('history_checked_at'),
        'activities_checked_at': meta.get('activities_checked_at'),
        'history_base_value': meta.get('history_base_value'), 'history_base_value_asof': meta.get('history_base_value_asof'),
        'unfunded_points_excluded': meta.get('unfunded_points_excluded'), 'account': {**observation,
            'change_since_tracking': float(equity-number(meta['initial_equity'])),
            'change_basis': 'equity change only; external cash flows are not return',
            'budget_usd': str(journal.budget()), 'budget_revision': journal.revision()},
        'pnl': {'ledger_status': ledger['status'], 'issues': ledger['issues'],
                'realized_gross': ledger['realized_gross'], 'unrealized_gross': ledger['unrealized_gross'],
                'non_trade_activity_count': len(non_trade), 'cashflow_review_required': bool(flows),
                'cashflow_net_since_tracking': float(sum((number(a['net_amount']) for a in flows), ZERO)),
                'unknown_fills': ledger['unknown_fills'],
                'basis': 'actual own FILL events, average cost, USD gross; fees/corporate actions require review'},
        'execution': execution_metrics(rows),
        'current_revision_execution': execution_metrics([r for r in rows if r['budget_revision'] == journal.revision()]),
        'orders': rows, 'positions': safe_positions, 'daily_history': daily, 'observations': observations,
        'comparison': comparison, 'latest_decisions': json.loads(decisions[0]) if decisions else None,
        'notes': ['체결률은 제출 주문 기준이며 취소 주문도 포함합니다.',
                  '전일 기준가 대비 변화는 가격 갭을 포함하며 순수 체결 슬리피지가 아닙니다.',
                  '비용은 추정치이며 브로커 계좌 손익에서 다시 차감하지 않습니다.',
                  '일별 계좌 이력은 API 시각 라벨을 유지하며 진행 중 날짜가 포함될 수 있습니다.']}


def collect_performance(client, root):
    root = Path(root)
    journal = Journal(root/'artifacts/paper_trading')
    try:
        with journal.lock():
            report = _collect(client, root, journal)
            atomic_json(root/'artifacts/paper_performance_public/status.json', report)
            (root/'artifacts/paper_performance_public/error.json').unlink(missing_ok=True)
            return report
    finally:
        journal.close()


def collect_safely(client, root):
    """Reporting faults must never suppress a risk check, place an order or clear a halt."""
    try:
        report = collect_performance(client, root)
        return {'status': report['status'], 'checked_at': report['checked_at'], 'sections': report['sections']}
    except Exception as error:
        report = {'status': 'error', 'checked_at': datetime.now(timezone.utc).isoformat(), 'error_type': type(error).__name__}
        try:
            atomic_json(Path(root)/'artifacts/paper_performance_public/error.json', report)
        except OSError:
            pass
        return report
