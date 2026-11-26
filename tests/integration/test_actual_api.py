import hashlib
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

pytest.importorskip('dotenv')
pytest.importorskip('exchange_calendars')

from apps.api.main import create_app
from quantcore.data.calendar import sessions
from quantcore.data.errors import DataUnavailable
from quantcore.data.providers.alpaca import SYMBOLS, regular_daily
from quantcore.paper.market import atomic_json


@pytest.fixture(scope='module')
def market_frames():
    schedule = sessions('2025-07-01', '2026-11-24')
    rows = []
    for k, symbol in enumerate(SYMBOLS):
        for i, (_, clock) in enumerate(schedule.iterrows()):
            for stamp in (clock['open'], clock['close']-pd.Timedelta(minutes=1)):
                price = 100+k*10+i*.1
                rows.append({'symbol': symbol, 't': stamp.isoformat(), 'o': price,
                             'h': price+1, 'l': price-1, 'c': price+.05, 'v': 100000})
    frame, _ = regular_daily(pd.DataFrame(rows), schedule, {s: [] for s in SYMBOLS})
    return frame, schedule


def publish(root, kind, name, frame, schedule, payload=None):
    path = root/kind/name
    path.mkdir(parents=True)
    frame.to_parquet(path/'prices.parquet', index=False)
    days = sorted(frame.session.unique())
    schedule.loc[days].to_csv(path/'calendar.csv')
    (path/'actions.json').write_text(json.dumps(payload or {}))
    atomic_json(path/'manifest.json', {'status': 'complete', 'data_mode': 'historical',
        'feed': 'iex', 'source': 'alpaca-iex-regular-1min', 'start': days[0], 'end': days[-1],
        'collected_at': '2026-11-25T00:00:00+00:00',
        'hashes': {n: hashlib.sha256((path/n).read_bytes()).hexdigest()
                   for n in ('prices.parquet', 'calendar.csv', 'actions.json')}})
    # Simulate an absolute host pointer viewed under a different container mount.
    atomic_json(path.parent/'latest.json', {'snapshot_directory': '/another/host/'+name})
    return path


@pytest.fixture
def actual(tmp_path, market_frames, monkeypatch):
    frame, schedule = market_frames
    base = frame[frame.session <= '2026-11-20'].copy()
    path = publish(tmp_path, 'real_equities', 'base', base, schedule)
    def network_forbidden(*args, **kwargs):
        raise AssertionError('analysis API must use the validated cache without credentials/network')
    monkeypatch.setattr('quantcore.data.providers.alpaca.AlpacaData.__init__', network_forbidden)
    with TestClient(create_app(data_source='alpaca', market_directory=tmp_path, token='actual-test'),
                    headers={'Authorization': 'Bearer actual-test'}) as client:
        yield client, tmp_path, path, base, frame, schedule


@pytest.mark.parametrize('path', ['/api/overview', '/api/assets/AAPL/prices', '/api/assets/AAPL/indicators',
    '/api/backtests/AAPL', '/api/portfolio', '/api/ml/AAPL', '/api/statistics', '/api/research/AAPL', '/api/monitoring'])
def test_actual_routes_share_actual_metadata(actual, path):
    client, _, _, _, _, _ = actual
    response = client.get(path)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['mode'] == 'historical' and data['source'] == 'alpaca-iex-regular-1min'
    assert data['dataset_version'] == client.get('/api/overview').json()['dataset_version']
    assert data['currency'] == 'USD'


def test_actual_values_and_missing_financial_data_are_honest(actual):
    client, _, _, base, _, _ = actual
    view = client.get('/api/overview').json()
    assert {a['symbol'] for a in view['assets']} == set(SYMBOLS)
    assert all(a['market_cap'] is None for a in view['assets']) and view['stale']
    frame = base[base.symbol == 'AAPL']
    prices = client.get('/api/assets/AAPL/prices').json()
    signal = client.get('/api/assets/AAPL/signal').json()
    indicators = client.get('/api/assets/AAPL/indicators').json()
    assert prices['prices'][-1]['close'] == float(frame.close.iloc[-1]) == signal['reference_close']
    assert signal['sma_60'] == pytest.approx(frame.close.tail(60).mean())
    assert indicators['values'][-1]['sma_60'] == pytest.approx(signal['sma_60'])
    assert signal['signal'] == 'buy' and signal['order_submission'] is False
    assert client.get('/api/assets/AAPL/fundamentals').json()['metrics'] == []
    assert client.get('/api/factors').json()['status'] == 'unavailable'
    assert client.post('/api/factors', json={'weights': {'momentum': -1}}).status_code == 422
    assert client.post('/api/orders', json={}).status_code == 404
    assert client.get('/api/overview', headers={'Authorization': ''}).status_code == 401
    assert client.get('/api/assets/QALPHA/prices').status_code == 404


def test_paper_update_refreshes_analysis_and_preserves_frozen_history(actual, monkeypatch):
    client, root, base_path, _, frame, schedule = actual
    observed_at = schedule['close'].iloc[-1] + pd.Timedelta(minutes=10)
    monkeypatch.setattr(pd.Timestamp, 'now', classmethod(lambda cls, tz=None: observed_at.tz_convert(tz)))
    old = client.get('/api/assets/AAPL/indicators').json()
    old_bytes = (base_path/'prices.parquet').read_bytes()
    window = sorted(frame.session.unique())[-100:]
    publish(root, 'paper_equities', 'new-session', frame[frame.session.isin(window)], schedule)
    current = client.get('/api/assets/AAPL/indicators').json()
    signal = client.get('/api/assets/AAPL/signal').json()
    assert old['dataset_version'] != current['dataset_version']
    assert current['dataset_version'] == signal['dataset_version']
    assert current['paper_snapshot_id'] == 'new-session'
    assert current['values'][-1]['close'] == float(frame[frame.symbol == 'AAPL'].close.iloc[-1])
    assert signal['sma_60'] == pytest.approx(frame[frame.symbol == 'AAPL'].close.tail(60).mean())
    assert not client.get('/api/overview').json()['stale']
    assert (base_path/'prices.parquet').read_bytes() == old_bytes


def test_actual_asof_filters_unavailable_bars(actual):
    client, _, _, base, _, _ = actual
    last = base[base.symbol == 'AAPL'].iloc[-1]
    cutoff = (last.available_at-pd.Timedelta(seconds=1)).isoformat()
    response = client.get('/api/assets/AAPL/prices', params={'as_of': cutoff}).json()
    assert all(pd.Timestamp(r['available_at']) <= pd.Timestamp(cutoff) for r in response['prices'])
    assert len(client.get('/api/assets/AAPL/prices', params={'as_of': '2020-01-01T00:00Z'}).json()['prices']) == 0
    assert client.get('/api/assets/AAPL/prices?as_of=2026-11-20T00:00:00').status_code == 422


def test_tampered_cache_returns_503_without_demo_fallback(actual):
    client, _, path, _, _, _ = actual
    assert client.get('/api/overview').status_code == 200
    with (path/'prices.parquet').open('ab') as handle:
        handle.write(b'tampered')
    response = client.get('/api/assets/AAPL/prices')
    assert response.status_code == 503 and response.json()['mode'] == 'historical'
    assert 'hash mismatch' in response.json()['detail']


def test_overlap_revision_is_not_silently_accepted(actual):
    client, root, _, base, _, schedule = actual
    altered = base[base.session.isin(sorted(base.session.unique())[-100:])].copy()
    changed = altered[(altered.symbol == 'AAPL') & (altered.session == '2026-11-20')].index
    altered.loc[changed, 'close'] += .1
    publish(root, 'paper_equities', 'revision', altered, schedule)
    response = client.get('/api/overview')
    assert response.status_code == 503 and 'revision conflict' in response.json()['detail']


def test_actual_websocket_reports_actual_universe(actual):
    client, _, _, _, _, _ = actual
    ticket = client.post('/api/ws-ticket').json()['ticket']
    with client.websocket_connect('/ws/market?ticket='+ticket, headers={'Origin': 'http://localhost:3000'}) as ws:
        data = ws.receive_json()
        assert data['kind'] == 'dataset_snapshot' and data['mode'] == 'historical'
        assert {a['symbol'] for a in data['assets']} == set(SYMBOLS)


def test_actual_mode_missing_cache_never_bootstraps_demo(tmp_path):
    with pytest.raises(DataUnavailable, match='no synthetic fallback'):
        with TestClient(create_app(data_source='alpaca', market_directory=tmp_path)):
            pass


def test_only_rolling_cache_reports_short_history_without_fake_results(tmp_path, market_frames):
    frame, schedule = market_frames
    window = sorted(frame.session.unique())[-100:]
    publish(tmp_path, 'paper_equities', 'rolling-only', frame[frame.session.isin(window)], schedule)
    with TestClient(create_app(data_source='alpaca', market_directory=tmp_path, token='')) as client:
        assert client.get('/health').json()['data_mode'] == 'historical'
        assert client.get('/api/ml/AAPL').json()['status'] == 'insufficient_history'
        assert client.get('/api/backtests/AAPL').json()['status'] == 'insufficient_history'
        assert client.get('/api/assets/AAPL/indicators').json()['values'][-1]['sma_200'] is None


def test_portfolio_and_risk_reports_are_read_only_and_missing_is_explicit(actual, monkeypatch):
    client, root, *_ = actual
    monkeypatch.setenv('QUANTCORE_PORTFOLIO_REPORT_DIR', str(root))
    monkeypatch.setenv('QUANTCORE_PAPER_RISK_DIR', str(root))
    assert client.get('/api/paper-risk').json()['status'] == 'unavailable'
    assert client.get('/api/portfolio-backtest').json()['status'] == 'unavailable'
    (root/'portfolio_backtest_results.json').write_text(json.dumps({'metadata': {'mode': 'historical'}, 'results': {}}))
    assert client.get('/api/portfolio-backtest').json()['metadata']['mode'] == 'historical'
    (root/'status.json').write_text(json.dumps({'checked_at': '2020-01-01T00:00:00+00:00', 'status': 'ok',
        'orders': [{'client_order_id': 'private'}], 'account_id': 'private', 'alerts': []}))
    public = client.get('/api/paper-risk').json()
    assert public['stale'] and 'orders' not in public and 'account_id' not in public
    assert 'private' not in json.dumps(public)
    (root/'status.json').write_text('invalid JSON')
    assert client.get('/api/paper-risk').json()['status'] == 'unavailable'
    assert client.post('/api/paper-risk', json={'resume': True}).status_code == 405


def test_paper_performance_api_redacts_private_ids_and_reports_failures(actual, monkeypatch):
    from datetime import datetime, timedelta, timezone
    client, root, *_ = actual
    monkeypatch.setenv('QUANTCORE_PAPER_PERFORMANCE_DIR', str(root))
    assert client.get('/api/paper-performance').json()['status'] == 'unavailable'
    at = datetime.now(timezone.utc)
    report = {'checked_at': at.isoformat(), 'status': 'ok', 'mode': 'paper',
        'account': {'equity': 100000, 'account_id': 'private-account'},
        'orders': [{'key': 'public-key', 'symbol': 'AAPL', 'client_order_id': 'private-order'}],
        'response': {'id': 'private-raw'}, 'pnl': {'realized_gross': 0}}
    (root/'status.json').write_text(json.dumps(report))
    result = client.get('/api/paper-performance')
    assert result.status_code == 200 and not result.json()['stale']
    assert 'private-' not in result.text
    (root/'error.json').write_text(json.dumps({'checked_at': (at+timedelta(seconds=1)).isoformat(), 'error_type': 'PaperError'}))
    assert client.get('/api/paper-performance').json()['collection_failed']
    assert client.post('/api/paper-performance', json={'submit': True}).status_code == 405
    assert client.get('/api/paper-performance', headers={'Authorization': ''}).status_code == 401


def test_reference_and_walk_forward_routes_are_read_only_and_hide_private_ids(actual,monkeypatch):
    client,root,*_=actual
    monkeypatch.setenv('QUANTCORE_CORPORATE_DIR',str(root))
    monkeypatch.setenv('QUANTCORE_PORTFOLIO_REPORT_DIR',str(root))
    assert client.get('/api/corporate-actions').json()['status']=='unavailable'
    assert client.get('/api/walk-forward').json()['status']=='unavailable'
    (root/'status.json').write_text(json.dumps({'checked_at':'2026-11-25T00:00:00+00:00','status':'reconciled',
        'classification':{'securities':{'AAPL':{'risk_group':'TECHNOLOGY','asset_id':'private'}}}}))
    assert 'asset_id' not in client.get('/api/corporate-actions').text
    (root/'walk_forward_results.json').write_text(json.dumps({'metadata':{'source':'actual'},'results':{},'decisions':[]}))
    assert client.get('/api/walk-forward').json()['metadata']['source']=='actual'
    assert client.post('/api/corporate-actions',json={}).status_code==405
    assert client.post('/api/walk-forward',json={}).status_code==405
