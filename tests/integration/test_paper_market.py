import hashlib
import json

import pandas as pd
import pytest

pytest.importorskip('exchange_calendars')
pytest.importorskip('dotenv')

from quantcore.data.calendar import sessions
from quantcore.data.providers.alpaca import SYMBOLS, load_snapshot, regular_daily
from quantcore.paper.market import atomic_json, refresh_snapshot


def minute_payload(schedule, price=100):
    bars = {}
    for symbol in SYMBOLS:
        bars[symbol] = [{'t': stamp.isoformat(), 'o': price, 'h': price+1, 'l': price-1, 'c': price, 'v': 100000}
                        for _, clock in schedule.iterrows()
                        for stamp in (clock['open'], clock['close']-pd.Timedelta(minutes=1))]
    return {'bars': bars, 'next_page_token': None}


def seed_snapshot(root, end='2026-11-23'):
    schedule = sessions(pd.Timestamp(end)-pd.Timedelta(days=180), end).iloc[-100:]
    payload = minute_payload(schedule)
    minutes = pd.concat([pd.DataFrame(rows).assign(symbol=s) for s, rows in payload['bars'].items()])
    frame, _ = regular_daily(minutes, schedule, {s: [] for s in SYMBOLS})
    # An old factor outside a rolling window must not create a discontinuity at the merge.
    frame['signal_close'] *= 10
    path = root/'datasets/real_equities/seed'
    path.mkdir(parents=True)
    frame.to_parquet(path/'prices.parquet', index=False)
    schedule.to_csv(path/'calendar.csv')
    (path/'actions.json').write_text('{}')
    manifest = {'status': 'complete', 'data_mode': 'historical', 'source': 'alpaca-iex-regular-1min',
                'feed': 'iex', 'start': schedule.index[0], 'end': end,
                'hashes': {n: hashlib.sha256((path/n).read_bytes()).hexdigest()
                           for n in ('prices.parquet', 'calendar.csv', 'actions.json')}}
    atomic_json(path/'manifest.json', manifest)
    atomic_json(path.parent/'latest.json', {'snapshot_directory': str(path)})
    return path


def test_incremental_update_split_basis_cache_and_frozen_research_inputs(tmp_path, monkeypatch):
    base = seed_snapshot(tmp_path)
    original = (base/'prices.parquet').read_bytes()
    calls = []
    schedule = sessions('2026-11-24', '2026-11-24')
    class Source:
        def __init__(self, env):
            pass
        def pages(self, path, params):
            calls.append((path, params))
            if path.endswith('/bars'):
                assert params['start'].startswith('2026-11-24') and params['feed'] == 'iex'
                yield minute_payload(schedule, 55)
            else:
                yield {'corporate_actions': {'forward_splits': [
                    {'id': 'past-split', 'symbol': 'NVDA', 'ex_date': '2026-11-24', 'new_rate': 2, 'old_rate': 1},
                    {'id': 'future-split', 'symbol': 'AAPL', 'ex_date': '2026-11-25', 'new_rate': 100, 'old_rate': 1}]}}
        def close(self):
            pass
    monkeypatch.setattr('quantcore.paper.market.AlpacaData', Source)
    updated = refresh_snapshot(tmp_path, None, '2026-11-25T02:00Z')
    frame, _, manifest = load_snapshot(updated)
    assert manifest['daily_rows'] == 500 and manifest['sessions'] == 100
    assert manifest['minute_rows_downloaded_this_update'] == 10
    assert manifest['base_hashes']['prices.parquet'] == hashlib.sha256(original).hexdigest()
    last = frame[frame.session == '2026-11-24'].set_index('symbol')
    assert last.loc['NVDA', 'signal_close'] == 110 and last.loc['AAPL', 'signal_close'] == 55
    assert (frame[frame.session < '2026-11-24'].signal_close == 100).all()
    assert (base/'prices.parquet').read_bytes() == original
    assert json.loads((base.parent/'latest.json').read_text())['snapshot_directory'] == str(base)
    assert refresh_snapshot(tmp_path, None, '2026-11-25T03:00Z') == updated
    assert len(calls) == 2  # Same completed session is read locally without another download.


@pytest.mark.parametrize('failure', ['unavailable', 'partial', 'bad_actions'])
def test_failed_daily_refresh_does_not_replace_latest(tmp_path, monkeypatch, failure):
    base = seed_snapshot(tmp_path)
    pointer = tmp_path/'datasets/paper_equities/latest.json'
    atomic_json(pointer, {'snapshot_directory': str(base)})
    prior = pointer.read_bytes()
    class Source:
        def __init__(self, env):
            pass
        def pages(self, path, params):
            if path.endswith('/bars'):
                payload = minute_payload(sessions('2026-11-24', '2026-11-24'))
                if failure == 'unavailable':
                    payload['bars'] = {}
                if failure == 'partial':
                    del payload['bars']['TSLA']
                yield payload
            else:
                yield {} if failure == 'bad_actions' else {'corporate_actions': {}}
        def close(self):
            pass
    monkeypatch.setattr('quantcore.paper.market.AlpacaData', Source)
    with pytest.raises(ValueError):
        refresh_snapshot(tmp_path, None, '2026-11-25T02:00Z')
    assert pointer.read_bytes() == prior
    assert list(pointer.parent.glob('*/failure.json'))


def test_fresh_seed_reuse_and_corruption_stop_before_network(tmp_path):
    base = seed_snapshot(tmp_path, '2026-11-24')
    assert refresh_snapshot(tmp_path, None, '2026-11-25T02:00Z') == base
    with (base/'prices.parquet').open('ab') as f:
        f.write(b'tampered')
    with pytest.raises(ValueError, match='hash mismatch'):
        refresh_snapshot(tmp_path, None, '2026-11-25T02:00Z')
