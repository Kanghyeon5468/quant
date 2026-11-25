import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest

from quantcore.paper.client import PaperClient, PaperError
from quantcore.paper.performance import (
    collect_performance,
    collect_safely,
    compare_backtest,
    history_rows,
    own_fill_ledger,
)
from quantcore.paper.reports import read_performance
from quantcore.paper.runner import Journal

NOW = datetime(2026, 11, 25, 15, 0, tzinfo=timezone.utc)


def record(cid, side, qty, price, filled=None):
    return {'client_id': cid, 'state': 'filled',
        'payload': {'symbol': 'AAPL', 'side': side, 'qty': str(qty), 'limit_price': str(price),
            'client_order_id': cid, 'type': 'limit', 'time_in_force': 'day', 'extended_hours': False},
        'response': {'id': 'broker-'+cid, 'filled_qty': str(qty if filled is None else filled),
            'submitted_at': '2026-11-25T14:00:00Z'}}


def fill(cid, ident, side, qty, price, second=0):
    return {'activity_type': 'FILL', 'id': ident, 'order_id': 'broker-'+cid, 'symbol': 'AAPL',
            'side': side, 'qty': str(qty), 'price': str(price),
            'transaction_time': (NOW-timedelta(minutes=20)+timedelta(seconds=second)).isoformat()}


def fixture_data():
    ids = ['qcp1-test-momentum-20261125-AAPL', 'qcp1-test-momentum-20261126-AAPL-r1',
           'qcp1-test-momentum-20261127-AAPL-r1']
    records = [record(ids[0], 'buy', 10, 101), record(ids[1], 'sell', 4, 119), record(ids[2], 'buy', 2, 111)]
    activities = [fill(ids[0], 'partial-1', 'buy', 3, 100), fill(ids[0], 'partial-2', 'buy', 7, 100, 1),
                  fill(ids[1], 'sale', 'sell', 4, 120, 2), fill(ids[2], 'new-buy', 'buy', 2, 110, 3)]
    positions = [{'symbol': 'AAPL', 'qty': '8', 'current_price': '125', 'avg_entry_price': '102.5',
                  'market_value': '1000', 'unrealized_pl': '180', 'unrealized_plpc': str(180/820)}]
    return records, activities, positions


def test_fill_level_partial_executions_realized_and_unrealized_reconcile():
    records, activities, positions = fixture_data()
    result = own_fill_ledger(records, list(reversed(activities)), positions)
    assert result['status'] == 'reconciled'
    assert result['inventory'] == {'AAPL': Decimal(8)}
    assert result['realized_gross'] == 80 and result['unrealized_gross'] == 180
    records[0]['response']['filled_qty'] = '9'
    missing = own_fill_ledger(records, activities, positions)
    assert missing['status'] == 'incomplete' and missing['realized_gross'] is None


def test_unknown_fills_and_missing_cost_basis_cannot_create_profit():
    records, activities, positions = fixture_data()
    wrong = {**activities[0], 'order_id': 'unmanaged', 'id': 'extra'}
    assert own_fill_ledger(records, activities+[wrong], positions)['unknown_fills'] == 1
    result = own_fill_ledger(records[1:], activities[2:], positions)
    assert result['realized_gross'] is None and result['unrealized_gross'] is None
    assert own_fill_ledger(records, activities, [])['status'] == 'incomplete'


def test_unfunded_history_is_not_a_trading_loss_and_future_data_is_rejected():
    epochs = [int((NOW-timedelta(days=n)).timestamp()) for n in (3, 2, 1)]
    payload = {'timestamp': epochs, 'equity': [0, 100000, 100010], 'profit_loss': [0, 0, 10], 'profit_loss_pct': [0, 0, .0001]}
    rows = history_rows(payload, NOW)
    assert len(rows) == 2 and rows[0]['equity'] == 100000 and rows[1]['broker_return'] == .0001
    payload['timestamp'][-1] = int((NOW+timedelta(days=1)).timestamp())
    with pytest.raises(ValueError, match='future'):
        history_rows(payload, NOW)
    payload['equity'].pop()
    with pytest.raises(ValueError, match='unaligned'):
        history_rows(payload, NOW)


class DataBroker:
    def __init__(self):
        self.records, self.activities, self.positions = fixture_data()
        self.calls, self.fail = [], None
        self.now = NOW
        self.account = {'id': 'account-private', 'currency': 'USD', 'equity': '100260', 'cash': '99260', 'last_equity': '100000'}

    def __call__(self, request):
        assert request.method == 'GET', 'collector must never submit/cancel orders'
        assert request.url.host == 'paper-api.alpaca.markets'
        path = request.url.path
        self.calls.append((path, dict(request.url.params)))
        if self.fail == path:
            return httpx.Response(503, json={})
        if path == '/v2/account':
            result = self.account
        elif path == '/v2/clock':
            result = {'timestamp': self.now.isoformat(), 'is_open': True}
        elif path == '/v2/positions':
            result = self.positions
        elif path == '/v2/account/activities':
            result = self.activities
        elif path == '/v2/account/portfolio/history':
            assert request.url.params['timeframe'] == '1D'
            assert 'period' not in request.url.params
            result = {'timestamp': [int((NOW-timedelta(days=i)).timestamp()) for i in (3, 2, 1)],
                'equity': [0, 100000, 100260], 'profit_loss': [0, 0, 260], 'profit_loss_pct': [0, 0, .0026],
                'base_value': 100000, 'base_value_asof': '2026-11-23'}
        else:
            raise AssertionError(path)
        return httpx.Response(200, json=result)


@pytest.fixture
def collector(tmp_path, monkeypatch):
    monkeypatch.setenv('ALPACA_API_KEY', 'paper-test')
    monkeypatch.setenv('ALPACA_SECRET_KEY', 'paper-test-secret')
    for key in ('APCA_API_BASE_URL', 'ALPACA_BASE_URL', 'ALPACA_API_URL'):
        monkeypatch.delenv(key, raising=False)
    broker = DataBroker()
    journal = Journal(tmp_path/'artifacts/paper_trading')
    journal.configure('account-private', 'momentum', Decimal(100000))
    for row in broker.records:
        journal.save(row['payload'], row['state'], row['response'])
    journal.db.execute('CREATE TABLE order_models (client_id TEXT PRIMARY KEY, data TEXT)')
    model = {'reference_close': 100, 'average_volume_20': 100000, 'policy': {}}
    for r in broker.records:
        journal.db.execute('INSERT INTO order_models VALUES (?, ?)', (r['client_id'], json.dumps(model)))
    journal.db.commit()
    journal.close()
    client = PaperClient(transport=httpx.MockTransport(broker))
    yield tmp_path, broker, client
    client.close()


def test_collection_is_idempotent_get_only_and_preserves_private_identity(collector):
    root, broker, client = collector
    result = collect_performance(client, root)
    assert result['pnl']['realized_gross'] == 80 and result['pnl']['unrealized_gross'] == 180
    assert result['execution']['share_fill_rate'] == 1 and result['execution']['orders'] == 3
    assert result['execution']['modeled_cost_estimate'] > 0
    assert result['orders'][0]['fill_average_price'] == 100
    assert result['orders'][0]['reference_change_bps'] == 0
    assert result['orders'][0]['first_fill_delay_seconds'] == 2400
    assert result['current_revision_execution']['orders'] == 1  # Revision0 excludes both revision1 orders.
    again = collect_performance(client, root)
    assert len(again['observations']) == 1 and len(again['daily_history']) == 2
    journal = Journal(root/'artifacts/paper_trading')
    assert journal.db.execute('SELECT COUNT(*) FROM performance_activities').fetchone()[0] == 4
    assert len(journal.records()) == 3
    journal.close()
    text = json.dumps(result)
    assert 'account-private' not in text and 'broker-qcp1' not in text
    assert all(r['client_id'] not in text for r in broker.records)


def test_cash_deposit_is_not_realized_trading_profit_and_unknown_action_degrades(collector):
    root, broker, client = collector
    collect_performance(client, root)
    broker.now += timedelta(minutes=5)
    broker.account.update(equity='110260', cash='109260')
    broker.activities += [{'id': 'cash', 'activity_type': 'CSD', 'created_at': broker.now.isoformat(), 'net_amount': '10000'}]
    report = collect_performance(client, root)
    assert report['account']['change_since_tracking'] == 10000
    assert report['pnl']['cashflow_net_since_tracking'] == 10000
    assert report['pnl']['realized_gross'] == 80
    assert report['comparison']['status'] == 'unavailable'
    broker.activities += [{'id': 'split', 'activity_type': 'SSP', 'date': '2026-11-25'}]
    report = collect_performance(client, root)
    assert report['pnl']['ledger_status'] == 'review_required' and report['pnl']['realized_gross'] is None


def test_collection_failure_retains_old_history_marks_unknown_and_does_not_block_trading(collector):
    root, broker, client = collector
    original = collect_performance(client, root)
    broker.now += timedelta(minutes=5)
    broker.fail = '/v2/account/activities'
    report = collect_performance(client, root)
    assert report['status'] == 'degraded' and report['pnl']['realized_gross'] is None
    assert report['activities_checked_at'] == original['activities_checked_at']
    broker.fail = '/v2/account'
    assert collect_safely(client, root)['status'] == 'error'
    public = read_performance(root/'artifacts/paper_performance_public')
    assert public['status'] == 'degraded' and public['stale']
    broker.fail = None
    collect_performance(client, root)
    assert not (root/'artifacts/paper_performance_public/error.json').exists()


def test_cross_account_performance_store_is_rejected(collector):
    root, broker, client = collector
    collect_performance(client, root)
    broker.account['id'] = 'other-private'
    with pytest.raises(ValueError, match='differs'):
        collect_performance(client, root)


def test_pagination_cycle_and_page_boundary_are_not_silently_truncated(monkeypatch):
    monkeypatch.setenv('ALPACA_API_KEY', 'paper-test')
    monkeypatch.setenv('ALPACA_SECRET_KEY', 'paper-test-secret')
    calls = []
    def transport(request):
        calls.append(request)
        return httpx.Response(200, json=[{'id': str(i)} for i in range(100)])
    client = PaperClient(transport=httpx.MockTransport(transport))
    with pytest.raises(PaperError, match='pagination cycle'):
        client.activities('2026-11-01', '2026-11-25')
    assert len(calls) == 2 and calls[-1].url.params['page_token'] == '99'
    with pytest.raises(PaperError, match='not allowed'):
        client.request('POST', '/v2/account/portfolio/history')
    client.close()


def test_comparison_requires_matching_completed_dates_and_uses_same_base(tmp_path):
    assert compare_backtest([], tmp_path, '2026-11-25')['status'] == 'unavailable'
    (tmp_path/'docs').mkdir()
    curve = [{'session': '2026-11-24', 'equity': 100000}, {'session': '2026-11-25', 'equity': 101000}]
    (tmp_path/'docs/portfolio_backtest_results.json').write_text(json.dumps({'results': {'momentum_risk_net': {'curve': curve}}}))
    history = [{'session': '2026-11-24', 'equity': 50000}, {'session': '2026-11-25', 'equity': 51000}]
    result = compare_backtest(history, tmp_path, '2026-11-24')
    assert result['status'] == 'available'
    assert result['points'][-1]['paper_index'] == 102 and result['points'][-1]['backtest_index'] == 101
    assert compare_backtest(history, tmp_path, '2026-11-25')['status'] == 'unavailable'
