import json
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

import httpx
import pandas as pd
import pytest

pytest.importorskip('exchange_calendars')
pytest.importorskip('dotenv')

from quantcore.data.calendar import sessions
from quantcore.data.providers.alpaca import SYMBOLS
from quantcore.paper.automation import resume, session_task, tick
from quantcore.paper.budget import change_budget
from quantcore.paper.client import PAPER_URL, AmbiguousOrder, PaperClient, PaperError, validate_order
from quantcore.paper.runner import Journal, cancel_own, make_plan, run_once, status


class Broker:
    def __init__(self):
        self.account = {'id': 'test-paper-account', 'status': 'ACTIVE', 'currency': 'USD',
                        'cash': '100000', 'buying_power': '200000', 'equity': '100000', 'last_equity': '100000'}
        self.clock = {'timestamp': '2026-11-24T21:10:00-05:00', 'is_open': False,
                      'next_open': '2026-11-25T09:30:00-05:00'}
        self.orders, self.positions, self.calls = {}, [], []
        self.failure, self.asset_tradable = None, True

    def __call__(self, request):
        assert request.url.host == 'paper-api.alpaca.markets'
        path = request.url.path
        self.calls.append((request.method, path))
        if request.method == 'POST':
            assert path == '/v2/orders'
            order = json.loads(request.content)
            if self.failure == 'reject':
                return httpx.Response(422, json={'message': 'test rejection'})
            if self.failure == 'timeout_not_received':
                raise httpx.ReadTimeout('test timeout')
            result = {**order, 'id': str(uuid5(NAMESPACE_URL, order['client_order_id'])),
                      'status': 'accepted', 'filled_qty': '0', 'filled_avg_price': None}
            self.orders[order['client_order_id']] = result
            if self.failure == 'timeout_received':
                raise httpx.ReadTimeout('test timeout after server receipt')
            return httpx.Response(200, json=result)
        if request.method == 'DELETE':
            item = next(r for r in self.orders.values() if r['id'] == path.rsplit('/', 1)[-1])
            item['status'] = 'pending_cancel' if self.failure == 'cancel_pending' else 'canceled'
            if self.failure == 'cancel_partial_fill':
                item['filled_qty'] = '1'
                self.positions.append({'symbol': item['symbol'], 'qty': '1', 'side': 'long'})
            return httpx.Response(204)
        if path == '/v2/account/portfolio/history':
            return httpx.Response(200, json={'timestamp': [], 'equity': [], 'profit_loss': [], 'profit_loss_pct': []})
        if path == '/v2/account/activities':
            return httpx.Response(200, json=[])
        if path == '/v2/account':
            return httpx.Response(200, json=self.account)
        if path == '/v2/clock':
            return httpx.Response(200, json=self.clock)
        if path == '/v2/positions':
            return httpx.Response(200, json=self.positions)
        if path == '/v2/orders':
            return httpx.Response(200, json=[r for r in self.orders.values() if r['status'] in ('accepted', 'pending_cancel')])
        if path == '/v2/orders:by_client_order_id':
            item = self.orders.get(request.url.params['client_order_id'])
            return httpx.Response(200, json=item) if item else httpx.Response(404, json={})
        if path.startswith('/v2/assets/'):
            return httpx.Response(200, json={'status': 'active', 'tradable': self.asset_tradable, 'class': 'us_equity'})
        raise AssertionError('unexpected endpoint')

    def fill_all(self):
        self.positions = []
        for row in self.orders.values():
            row.update(status='filled', filled_qty=row['qty'], filled_avg_price='100')
            self.positions.append({'symbol': row['symbol'], 'qty': row['qty'], 'side': 'long'})


@pytest.fixture
def setup_paper(tmp_path, monkeypatch):
    for name in ['APCA_API_BASE_URL', 'ALPACA_BASE_URL', 'ALPACA_API_URL']:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('ALPACA_API_KEY', 'unit-test-key')
    monkeypatch.setenv('ALPACA_SECRET_KEY', 'unit-test-secret')
    schedule = sessions('2026-07-01', '2026-11-24')
    rows = []
    for s in SYMBOLS:
        for i, (day, clock) in enumerate(schedule.iterrows()):
            rows.append({'symbol': s, 'session': day, 'timestamp': clock['close'],
                         'available_at': clock['close']+pd.Timedelta(minutes=1),
                         'close': 99+i*.01, 'signal_close': 99+i*.01, 'volume': 100000})
    frame = pd.DataFrame(rows)
    manifest = {'end': '2026-11-24', 'feed': 'iex', 'source': 'alpaca-iex-regular-1min', 'hashes': {'test': 'hash'}}
    snapshot = tmp_path/'snapshot'
    snapshot.mkdir()
    (snapshot/'actions.json').write_text('{}')
    monkeypatch.setattr('quantcore.paper.runner.load_snapshot', lambda p: (frame, {}, manifest))
    broker = Broker()
    client = PaperClient(transport=httpx.MockTransport(broker))
    permissive = {'sector_weight': 1, 'correlated_weight': 1, 'portfolio_volatility': 5, 'gross_weight': 1, 'position_weight': 1}
    for directory in (tmp_path/'paper', tmp_path/'artifacts/paper_trading'):
        directory.mkdir(parents=True, exist_ok=True)
        (directory/'risk_limits.json').write_text(json.dumps(permissive))
    pointer = tmp_path/'datasets/real_equities/latest.json'
    pointer.parent.mkdir(parents=True)
    pointer.write_text(json.dumps({'snapshot_directory': str(snapshot)}))
    yield client, broker, snapshot, tmp_path/'paper', frame, manifest
    client.close()


def test_dry_plan_submit_partial_fill_restart_and_cancel(setup_paper):
    client, broker, snapshot, directory, _, _ = setup_paper
    dry = run_once(client, directory, snapshot)
    assert len(dry['orders']) == 5 and all(o['side'] == 'buy' for o in dry['orders'])
    assert not any(m == 'POST' for m, _ in broker.calls)
    assert Decimal(dry['max_new_buy_limit_notional_usd']) <= 5000
    first = run_once(client, directory, snapshot, submit=True)
    assert len(first['journal']) == 5
    assert all(r['state'] == 'accepted' and r['response']['filled_qty'] == '0' for r in first['journal'])
    run_once(client, directory, snapshot, submit=True)
    assert sum(m == 'POST' for m, _ in broker.calls) == 5
    # Broker positions can be partially filled; only the unfilled remainder is reserved.
    one = next(iter(broker.orders.values()))
    one['filled_qty'] = '1'
    broker.positions = [{'symbol': one['symbol'], 'qty': '1', 'side': 'long'}]
    run_once(client, directory, snapshot, submit=True)
    assert sum(m == 'POST' for m, _ in broker.calls) == 5
    result = cancel_own(client, directory)
    assert all(r['state'] == 'canceled' for r in result)
    assert sum(m == 'DELETE' for m, _ in broker.calls) == 5
    # Canceled intents are not silently resubmitted in the same session.
    run_once(client, directory, snapshot, submit=True)
    assert sum(m == 'POST' for m, _ in broker.calls) == 5


def test_confirmed_fills_reconcile_as_owned_positions(setup_paper):
    client, broker, snapshot, directory, _, _ = setup_paper
    run_once(client, directory, snapshot, submit=True)
    broker.fill_all()
    result = status(client, directory)
    assert len(result['positions']) == 5 and all(r['state'] == 'filled' for r in result['journal'])
    assert len(result['modeled_fill_costs']) == 5
    assert all(r['modeled_total_cost'] > 0 and r['status'] == 'estimate_only' for r in result['modeled_fill_costs'])
    again = run_once(client, directory, snapshot, submit=True)
    assert not again['orders']
    assert sum(m == 'POST' for m, _ in broker.calls) == 5


@pytest.mark.parametrize('received', [True, False])
def test_ambiguous_post_never_blindly_retries(setup_paper, received):
    client, broker, snapshot, directory, _, _ = setup_paper
    broker.failure = 'timeout_received' if received else 'timeout_not_received'
    if received:
        result = run_once(client, directory, snapshot, submit=True)
        assert len(result['journal']) == 5
    else:
        with pytest.raises(AmbiguousOrder, match='without retry'):
            run_once(client, directory, snapshot, submit=True)
        with pytest.raises(AmbiguousOrder, match='absent at broker'):
            run_once(client, directory, snapshot, submit=True)
        assert sum(m == 'POST' for m, _ in broker.calls) == 1


def test_broker_rejection_and_kill_file_stop_new_orders(setup_paper):
    client, broker, snapshot, directory, _, _ = setup_paper
    directory.mkdir(exist_ok=True)
    (directory/'STOP').touch()
    with pytest.raises(PaperError, match='STOP'):
        run_once(client, directory, snapshot, submit=True)
    assert not any(m == 'POST' for m, _ in broker.calls)
    (directory/'STOP').unlink()
    broker.failure = 'reject'
    with pytest.raises(PaperError, match='422'):
        run_once(client, directory, snapshot, submit=True)
    assert sum(m == 'POST' for m, _ in broker.calls) == 1
    result = run_once(client, directory, snapshot)
    assert result['journal'][0]['state'] == 'rejected_locally'


@pytest.mark.parametrize('condition', ['blocked', 'cash', 'unmanaged_position', 'unmanaged_order', 'asset'])
def test_preflight_rejects_unsafe_account_or_asset(setup_paper, condition):
    client, broker, snapshot, directory, _, _ = setup_paper
    if condition == 'blocked':
        broker.account['trading_blocked'] = True
    elif condition == 'cash':
        broker.account['cash'] = '1'
    elif condition == 'unmanaged_position':
        broker.positions = [{'symbol': 'AAPL', 'qty': '1', 'side': 'long'}]
    elif condition == 'unmanaged_order':
        broker.orders['other'] = {'client_order_id': 'other', 'status': 'accepted', 'symbol': 'AAPL'}
    else:
        broker.asset_tradable = False
    if condition == 'cash':
        result = run_once(client, directory, snapshot, submit=True)
        assert not result['orders'] and all(d['decision'] == 'deferred_budget' for d in result['decisions'])
    else:
        with pytest.raises(PaperError):
            run_once(client, directory, snapshot, submit=True)
    assert not any(m == 'POST' for m, _ in broker.calls)


@pytest.mark.parametrize('condition', ['stale', 'future', 'split', 'missed_open', 'calendar', 'budget', 'strategy'])
def test_signal_and_session_checks_precede_submission(setup_paper, condition):
    client, broker, snapshot, directory, frame, manifest = setup_paper
    kwargs = {}
    if condition == 'stale':
        manifest['end'] = '2026-11-23'
    elif condition == 'future':
        frame.loc[frame.index[-1], 'available_at'] = pd.Timestamp('2026-11-26T00:00Z')
    elif condition == 'split':
        (snapshot/'actions.json').write_text(json.dumps({'forward_splits': [{'symbol': 'NVDA', 'ex_date': '2026-11-25'}]}))
    elif condition == 'missed_open':
        broker.clock.update(is_open=True, timestamp='2026-11-25T10:00:00-05:00')
    elif condition == 'calendar':
        broker.clock['next_open'] = '2026-11-26T09:30:00-05:00'  # Thanksgiving holiday.
    elif condition == 'budget':
        kwargs['budget'] = Decimal(100001)
    else:
        kwargs['strategy'] = 'buy_hold'
    with pytest.raises(PaperError):
        run_once(client, directory, snapshot, submit=True, **kwargs)
    assert not any(m == 'POST' for m, _ in broker.calls)


def test_daily_signal_can_reduce_owned_inventory_without_shorting(setup_paper):
    client, broker, snapshot, directory, frame, _ = setup_paper
    run_once(client, directory, snapshot, submit=True)
    broker.fill_all()
    # Replay a separate same-day planning context with the entry records retained.
    # Delete same-session IDs only from the synthetic test ledger and assign previous-session IDs.
    journal = Journal(directory)
    for record in journal.records():
        old = record['payload']['client_order_id']
        new = old.replace('20261125', '20261124')
        response = broker.orders.pop(old)
        response['client_order_id'] = new
        broker.orders[new] = response
        payload = {**record['payload'], 'client_order_id': new}
        journal.db.execute('DELETE FROM orders WHERE client_id=?', (old,))
        journal.save(payload, 'filled', response)
    frame.loc[frame.session == '2026-11-24', 'signal_close'] = 1
    plan = make_plan(snapshot, client.context(), journal)
    assert len(plan['orders']) == 5 and all(o['side'] == 'sell' for o in plan['orders'])
    for order in plan['orders']:
        owned = next(p['qty'] for p in broker.positions if p['symbol'] == order['symbol'])
        assert Decimal(order['qty']) <= Decimal(owned)
    journal.close()


def test_journal_account_config_lock_and_broker_intent_mismatch(setup_paper):
    client, broker, snapshot, directory, _, _ = setup_paper
    run_once(client, directory, snapshot, submit=True)
    with pytest.raises(PaperError, match='different account'):
        run_once(client, directory, snapshot, budget=1000)
    a, b = Journal(directory), Journal(directory)
    with a.lock(), pytest.raises(PaperError, match='another paper runner'):
        with b.lock():
            pass
    a.close()
    b.close()
    next(iter(broker.orders.values()))['qty'] = '999'
    with pytest.raises(AmbiguousOrder, match='differs'):
        status(client, directory)


def test_client_blocks_live_urls_unknown_routes_and_redirects(setup_paper, monkeypatch):
    client, _, _, _, _, _ = setup_paper
    for method, path in [('GET', 'https://api.alpaca.markets/v2/account'), ('POST', '/v2/account'),
                         ('DELETE', '/v2/orders'), ('GET', '/v2/assets/BTCUSD')]:
        with pytest.raises(PaperError, match='not allowed'):
            client.request(method, path)
    client.client.base_url = 'https://api.alpaca.markets'
    with pytest.raises(PaperError, match='host guard'):
        client.context()
    monkeypatch.setenv('APCA_API_BASE_URL', 'https://api.alpaca.markets')
    with pytest.raises(PaperError, match='not the paper server'):
        PaperClient()
    monkeypatch.setenv('APCA_API_BASE_URL', PAPER_URL)
    redirected = PaperClient(transport=httpx.MockTransport(lambda r: httpx.Response(302, headers={'location': 'https://api.alpaca.markets'})))
    with pytest.raises(PaperError, match='302'):
        redirected.context()
    redirected.close()
    for name in ['ALPACA_API_KEY', 'ALPACA_SECRET_KEY', 'APCA_API_KEY_ID', 'APCA_API_SECRET_KEY',
                 'ALPACA_PAPER_API_KEY', 'ALPACA_PAPER_SECRET_KEY']:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(PaperError, match='credentials missing'):
        PaperClient()


@pytest.mark.parametrize('field,value', [('qty', '0'), ('qty', '-1'), ('qty', '1.1'),
    ('limit_price', 'NaN'), ('limit_price', '.001'), ('limit_price', '-1'),
    ('side', 'short'), ('symbol', 'BTCUSD'), ('type', 'market'), ('extended_hours', True),
    ('time_in_force', 'gtc'), ('client_order_id', 'someone-else')])
def test_order_policy_rejects_bypass_fields(field, value):
    order = {'symbol': 'AAPL', 'qty': '1', 'side': 'buy', 'type': 'limit', 'limit_price': '100.00',
             'extended_hours': False, 'time_in_force': 'day', 'client_order_id': 'qcp1-test'}
    order[field] = value
    with pytest.raises((ValueError, PaperError)):
        validate_order(order)


def test_per_symbol_notional_is_a_hard_buy_ceiling():
    order = {'symbol': 'AAPL', 'qty': '201', 'side': 'buy', 'type': 'limit', 'limit_price': '100.00',
             'extended_hours': False, 'time_in_force': 'day', 'client_order_id': 'qcp1-test'}
    with pytest.raises(ValueError, match='20,000'):
        validate_order(order)


@pytest.mark.parametrize('stamp,is_open,next_open,expected', [
    ('2026-11-24T16:05:00-05:00', False, '2026-11-25T09:30:00-05:00', None),
    ('2026-11-24T16:10:00-05:00', False, '2026-11-25T09:30:00-05:00', '2026-11-25'),
    ('2026-11-25T09:34:00-05:00', True, '2026-11-27T09:30:00-05:00', '2026-11-25'),
    ('2026-11-25T09:36:00-05:00', True, '2026-11-27T09:30:00-05:00', None),
    ('2026-11-26T11:00:00-05:00', False, '2026-11-27T09:30:00-05:00', '2026-11-27'),
    ('2026-11-27T13:05:00-05:00', False, '2026-11-30T09:30:00-05:00', None),
    ('2026-11-27T13:11:00-05:00', False, '2026-11-30T09:30:00-05:00', '2026-11-30'),
    ('2026-03-09T09:32:00-04:00', True, '2026-03-10T09:30:00-04:00', '2026-03-09'),
])
def test_automation_calendar_windows(stamp, is_open, next_open, expected):
    task = session_task({'timestamp': stamp, 'is_open': is_open, 'next_open': next_open})
    assert (task['execution_session'] if task else None) == expected


def worker_setup(setup_paper, monkeypatch):
    _, broker, snapshot, old_directory, frame, manifest = setup_paper
    root = old_directory.parent
    broker.account['equity'] = '100000'
    monkeypatch.setattr('quantcore.paper.automation.PaperClient',
                        lambda env: PaperClient(transport=httpx.MockTransport(broker)))
    refreshes = []
    def refresh(*args):
        refreshes.append(args)
        return snapshot
    monkeypatch.setattr('quantcore.paper.automation.refresh_snapshot', refresh)
    return root, broker, frame, manifest, refreshes


def test_automatic_entry_monitor_and_next_session_exit(setup_paper, monkeypatch):
    root, broker, frame, manifest, refreshes = worker_setup(setup_paper, monkeypatch)
    first = tick(root, None)
    assert first['phase'] == 'evaluated' and first['last_evaluation']['new_orders'] == 5
    again = tick(root, None)
    assert again['phase'] == 'session_already_evaluated' and len(refreshes) == 2
    assert sum(m == 'POST' for m, _ in broker.calls) == 5
    broker.fill_all()
    broker.account['equity'] = '100123'
    monitored = tick(root, None)
    assert monitored['paper_account_equity_change'] == '123'
    assert all(o['status'] == 'filled' for o in monitored['orders'])
    # A new completed session can turn the existing strategy off and submit owned-share exits.
    new_clock = sessions('2026-11-25', '2026-11-25').iloc[0]
    additions = frame[frame.session == '2026-11-24'].copy()
    additions['session'] = '2026-11-25'
    additions['timestamp'] = new_clock['close']
    additions['available_at'] = new_clock['close']+pd.Timedelta(minutes=1)
    additions['signal_close'] = 1.
    for _, row in additions.iterrows():
        frame.loc[len(frame)] = row
    manifest['end'] = '2026-11-25'
    broker.clock.update(timestamp='2026-11-25T16:11:00-05:00', next_open='2026-11-27T09:30:00-05:00')
    result = tick(root, None)
    assert result['phase'] == 'evaluated' and result['last_evaluation']['execution_session'] == '2026-11-27'
    assert len(refreshes) == 4 and sum(m == 'POST' for m, _ in broker.calls) == 10
    assert sum(o['side'] == 'sell' for o in broker.orders.values()) == 5


def test_automation_pause_resume_and_ambiguous_order_latch(setup_paper, monkeypatch):
    root, broker, _, _, _ = worker_setup(setup_paper, monkeypatch)
    directory = root/'artifacts/paper_trading'
    directory.mkdir(parents=True, exist_ok=True)
    (directory/'STOP').touch()
    assert tick(root, None)['phase'] == 'paused'
    assert not any(m == 'POST' for m, _ in broker.calls)
    resume(directory)
    broker.failure = 'timeout_not_received'
    assert tick(root, None)['phase'] == 'blocked'
    assert tick(root, None)['blocked']
    assert sum(m == 'POST' for m, _ in broker.calls) == 1
    resume(directory)
    assert tick(root, None)['phase'] == 'blocked'  # Resume cannot bypass the unresolved durable intent.
    assert sum(m == 'POST' for m, _ in broker.calls) == 1


def test_automation_monitor_only_and_bounded_transient_retry(setup_paper, monkeypatch):
    root, broker, _, _, refreshes = worker_setup(setup_paper, monkeypatch)
    broker.clock.update(is_open=True, timestamp='2026-11-25T12:00:00-05:00')
    assert tick(root, None)['phase'] == 'monitoring' and not refreshes
    def fail(*args):
        raise PaperError('paper API network request failed', retryable=True)
    monkeypatch.setattr('quantcore.paper.automation.status', fail)
    retry = tick(root, None)
    assert retry['phase'] == 'retry_wait' and retry['consecutive_failures'] == 1
    state = root/'artifacts/paper_trading/automation/state.json'
    current = json.loads(state.read_text())
    current['consecutive_failures'] = 3
    state.write_text(json.dumps(current))
    assert tick(root, None)['phase'] == 'blocked'
    assert not any(m == 'POST' for m, _ in broker.calls)


def test_budget_shortfall_defers_entries_but_preserves_exits(setup_paper):
    client, broker, snapshot, directory, frame, _ = setup_paper
    frame.loc[(frame.symbol == 'NVDA') & (frame.session == '2026-11-24'), 'signal_close'] = 1.
    run_once(client, directory, snapshot, submit=True)
    broker.fill_all()
    journal = Journal(directory)
    journal.reconcile(client)
    # Clear only today's synthetic deduplication IDs for planning another session.
    for row in journal.records():
        journal.db.execute('UPDATE orders SET client_id=? WHERE client_id=?',
                           (row['client_id'].replace('20261125', '20261124'), row['client_id']))
    journal.db.commit()
    broker.account['cash'] = '1'
    frame.loc[frame.session == '2026-11-24', 'close'] = 120.
    frame.loc[(frame.symbol == 'NVDA') & (frame.session == '2026-11-24'), 'signal_close'] = 120.
    frame.loc[(frame.symbol == 'AAPL') & (frame.session == '2026-11-24'), 'signal_close'] = 1.
    plan = make_plan(snapshot, client.context(), journal)
    assert any(o['side'] == 'sell' and o['symbol'] == 'AAPL' for o in plan['orders'])
    assert not any(o['side'] == 'buy' for o in plan['orders'])
    assert next(d for d in plan['decisions'] if d['symbol'] == 'NVDA')['decision'] == 'deferred_budget'
    journal.close()


def test_launchagent_has_fixed_interval_login_and_no_secret_values(tmp_path):
    from scripts.manage_paper_automation import make_plist
    spec = make_plist(tmp_path, tmp_path/'authorized.env')
    assert spec['RunAtLoad'] and spec['StartInterval'] == 300 and spec['Umask'] == 0o077
    assert spec['ProgramArguments'][3] == 'tick'
    assert 'unit-test-secret' not in str(spec)
    assert 'unit-test-key' not in str(spec)


def test_budget_migration_preserves_history_and_restarts_with_revision_deduplication(setup_paper, monkeypatch):
    client, broker, snapshot, _, _, _ = setup_paper
    root, _, _, _, _ = worker_setup(setup_paper, monkeypatch)
    directory = root/'artifacts/paper_trading'
    assert tick(root, None)['last_evaluation']['new_orders'] == 5
    result = change_budget(client, directory, snapshot, 100000, execute=True, resume_after=True)
    assert result['old_budget_usd'] == '5000' and result['budget_usd'] == '100000'
    assert result['budget_revision'] == 1 and not (directory/'STOP').exists()
    assert len(result['journal']) == 10
    assert sum(r['state'] == 'canceled' for r in result['journal']) == 5
    current = [r for r in result['journal'] if r['state'] == 'accepted']
    assert len(current) == 5 and all(r['client_id'].endswith('-r1') for r in current)
    assert all(Decimal(r['payload']['qty'])*Decimal(r['payload']['limit_price']) <= 20000 for r in current)
    journal = Journal(directory)
    assert journal.budget() == 100000 and journal.revision() == 1
    assert journal.db.execute('SELECT COUNT(*) FROM budget_changes').fetchone()[0] == 1
    journal.close()
    assert list((directory/'budget_changes').glob('*.sqlite3'))
    again = change_budget(client, directory, snapshot, 100000, execute=True, resume_after=True)
    assert not again['orders'] and again['budget_revision'] == 1
    assert tick(root, None)['phase'] == 'session_already_evaluated'
    assert sum(m == 'POST' for m, _ in broker.calls) == 10
    assert sum(m == 'DELETE' for m, _ in broker.calls) == 5


def test_partial_fill_during_cancel_is_not_bought_twice(setup_paper):
    client, broker, snapshot, directory, _, _ = setup_paper
    old = run_once(client, directory, snapshot, submit=True)
    broker.failure = 'cancel_partial_fill'
    result = change_budget(client, directory, snapshot, 100000, execute=True, resume_after=True)
    for r in result['journal']:
        if r['state'] == 'accepted':
            decision = next(d for d in run_once(client, directory, snapshot)['decisions']
                            if d['symbol'] == r['payload']['symbol'])
            assert Decimal(r['payload']['qty'])+1 == Decimal(decision['desired_qty'])
    assert len(old['journal']) == 5 and len(result['journal']) == 10
    assert sum(r['response']['filled_qty'] == '1' for r in result['journal']) == 5


def test_unconfirmed_cancel_cannot_raise_budget_or_submit_replacements(setup_paper, monkeypatch):
    client, broker, snapshot, directory, _, _ = setup_paper
    run_once(client, directory, snapshot, submit=True)
    broker.failure = 'cancel_pending'
    monkeypatch.setattr('quantcore.paper.budget.time.sleep', lambda seconds: None)
    with pytest.raises(PaperError, match='cancellation not final'):
        change_budget(client, directory, snapshot, 100000, execute=True, resume_after=True)
    journal = Journal(directory)
    assert journal.budget() == 5000 and journal.revision() == 0
    journal.close()
    assert (directory/'STOP').exists()
    assert sum(m == 'POST' for m, _ in broker.calls) == 5


def test_failed_replacement_keeps_automation_paused_and_unknown_intent(setup_paper):
    client, broker, snapshot, directory, _, _ = setup_paper
    run_once(client, directory, snapshot, submit=True)
    broker.failure = 'timeout_not_received'
    with pytest.raises(AmbiguousOrder):
        change_budget(client, directory, snapshot, 100000, execute=True, resume_after=True)
    journal = Journal(directory)
    assert journal.budget() == 100000 and journal.revision() == 1
    assert any(r['state'] == 'unknown' for r in journal.records())
    journal.close()
    assert (directory/'STOP').exists()
    assert sum(m == 'POST' for m, _ in broker.calls) == 6


def test_large_paper_buying_power_does_not_override_available_cash(setup_paper):
    client, broker, snapshot, directory, _, _ = setup_paper
    broker.account.update(cash='1000', buying_power='200000')
    result = run_once(client, directory, snapshot, budget=100000, submit=True)
    assert 0 < Decimal(result['max_new_buy_limit_notional_usd']) <= 1000
    assert any(d['decision'] == 'deferred_budget' for d in result['decisions'])
    assert sum(Decimal(r['payload']['qty'])*Decimal(r['payload']['limit_price']) for r in result['journal']) <= 1000


def test_budget_change_rejects_unrelated_orders_and_unauthorized_ceiling(setup_paper):
    client, broker, snapshot, directory, _, _ = setup_paper
    run_once(client, directory, snapshot, submit=True)
    broker.orders['other'] = {'client_order_id': 'other', 'status': 'accepted', 'symbol': 'AAPL'}
    with pytest.raises(PaperError, match='unmanaged'):
        change_budget(client, directory, snapshot, 100000, execute=True, resume_after=True)
    assert not any(m == 'DELETE' for m, _ in broker.calls)
    with pytest.raises(PaperError, match='100,000'):
        change_budget(client, directory, snapshot, 100001)


def test_risk_cancels_pending_buys_latches_and_preserves_exit_permission(setup_paper):
    from quantcore.paper.runner import monitor_risk
    client, broker, snapshot, directory, _, _ = setup_paper
    initial = run_once(client, directory, snapshot, budget=100000, submit=True)
    assert len(initial['orders']) == 5
    broker.account['equity'] = '97000'
    risk = monitor_risk(client, directory, snapshot)
    assert risk['daily_latched'] and len(risk['cancel_actions']) == 5
    assert 'daily_loss' in risk['halt_rules']
    assert all(o['status'] == 'canceled' for o in broker.orders.values())
    broker.account['equity'] = '100000'
    recovered = monitor_risk(client, directory, snapshot)
    assert recovered['daily_latched'] and 'daily_loss' in recovered['halt_rules']
    journal = Journal(directory)
    assert journal.db.execute('SELECT MAX(count) FROM risk_alerts').fetchone()[0] >= 2
    journal.close()
    assert sum(m == 'POST' for m, _ in broker.calls) == 5


def test_risk_missing_equity_fails_closed_without_new_order(setup_paper):
    client, broker, snapshot, directory, _, _ = setup_paper
    broker.account.pop('equity')
    report = run_once(client, directory, snapshot, submit=True)
    assert not report['orders'] and report['risk']['data_status'] == 'unavailable'
    assert report['risk']['halt_rules'] == ['risk_data_unavailable']
    assert not any(m == 'POST' for m, _ in broker.calls)


def test_paper_and_portfolio_share_the_same_order_policy(setup_paper):
    from quantcore.strategies.orders import OrderPolicy, slot_orders
    client, _, snapshot, directory, frame, _ = setup_paper
    plan = run_once(client, directory, snapshot, budget=100000)
    histories = {s: frame[frame.symbol == s].copy() for s in SYMBOLS}
    expected = slot_orders(histories, dict.fromkeys(SYMBOLS, 0), 100000, 100000, 'momentum', policy=OrderPolicy())
    assert [{k: v for k, v in o.items() if k != 'client_order_id'} for o in plan['orders']] == expected['orders']
    assert plan['order_policy_version'] == expected['order_policy_version']


def test_unconfirmed_risk_cancel_blocks_new_orders(setup_paper):
    from quantcore.paper.runner import monitor_risk
    client, broker, snapshot, directory, _, _ = setup_paper
    run_once(client, directory, snapshot, budget=100000, submit=True)
    broker.account['equity'] = '97000'
    broker.failure = 'cancel_pending'
    with pytest.raises(PaperError, match='cancellation not yet confirmed'):
        monitor_risk(client, directory, snapshot)
    assert sum(m == 'POST' for m, _ in broker.calls) == 5
    assert sum(m == 'DELETE' for m, _ in broker.calls) == 5


def test_monitor_unreadable_snapshot_cancels_own_buys(setup_paper, monkeypatch):
    from quantcore.paper.runner import monitor_risk
    client, broker, snapshot, directory, _, _ = setup_paper
    run_once(client, directory, snapshot, submit=True)
    def broken(path):
        raise ValueError('corrupted input')
    monkeypatch.setattr('quantcore.paper.runner.load_snapshot', broken)
    report = monitor_risk(client, directory, snapshot)
    assert report['data_status'] == 'unavailable' and len(report['cancel_actions']) == 5
    assert all(o['status'] == 'canceled' for o in broker.orders.values())


def test_order_evidence_is_durable_before_post_and_preserved_on_repeat(setup_paper, monkeypatch):
    client, _, snapshot, directory, _, _ = setup_paper
    original = client.request
    seen = []
    def request(method, path, **kwargs):
        if method == 'POST':
            journal = Journal(directory)
            row = journal.db.execute('SELECT data FROM order_evidence WHERE client_id=?',
                                    (kwargs['order']['client_order_id'],)).fetchone()
            journal.close()
            assert row
            evidence = json.loads(row[0])
            assert evidence['evidence_status'] == 'captured_before_submission'
            assert evidence['signal_close'] > evidence['sma_60']
            seen.append(evidence)
        return original(method, path, **kwargs)
    monkeypatch.setattr(client, 'request', request)
    run_once(client, directory, snapshot, submit=True)
    run_once(client, directory, snapshot, submit=True)
    assert len(seen) == 5
    journal = Journal(directory)
    stored = [json.loads(r[0]) for r in journal.db.execute('SELECT data FROM order_evidence')]
    assert sorted(r['captured_at'] for r in stored) == sorted(r['captured_at'] for r in seen)
    journal.close()
