import json

import numpy as np
import pandas as pd
import pytest

pytest.importorskip('exchange_calendars')
pytest.importorskip('dotenv')

from quantcore.data.calendar import sessions
from quantcore.data.providers.alpaca import SYMBOLS, collect_snapshot, load_snapshot
from quantcore.research.real_equities import export_actual, latest_snapshot


def test_historical_pipeline_with_mock_transport_and_hash_rejection(tmp_path, monkeypatch):
    schedule = sessions('2025-07-01', '2026-11-24')
    payload = {}
    for symbol in SYMBOLS:
        rows = []
        for i, (_, clock) in enumerate(schedule.iterrows()):
            price = 100+np.sin(i/10)+i*.01
            for stamp in [clock['open'], clock['close']-pd.Timedelta(minutes=1)]:
                rows.append({'t': stamp.isoformat(), 'o': price, 'h': price+1, 'l': price-1, 'c': price, 'v': 100000})
        payload[symbol] = rows
    class MockSource:
        def __init__(self, env_file):
            pass
        def pages(self, path, params):
            if path == '/v2/stocks/bars':
                assert params['timeframe'] == '1Min' and params['adjustment'] == 'raw' and params['feed'] == 'iex'
                yield {'bars': payload, 'next_page_token': None}
            else:
                assert path == '/v1/corporate-actions'
                yield {'corporate_actions': {}, 'next_page_token': None}
        def close(self):
            pass
    monkeypatch.setattr('quantcore.data.providers.alpaca.AlpacaData', MockSource)
    root = tmp_path
    (root/'docs').mkdir()
    directory = collect_snapshot(root/'datasets/real_equities', None, as_of='2026-11-25T01:30:00Z')
    assert latest_snapshot(root) == directory
    frame, actions, manifest = load_snapshot(directory)
    assert len(frame) == 5*len(schedule) and manifest['data_mode'] == 'historical'
    report = export_actual(root, directory)
    assert len(report['results']) == len(report['validation']) == 15
    assert all(row['cash_inventory_nav_reconciled'] and row['future_mutation_invariant'] for row in report['validation'])
    path = directory/'prices.parquet'
    path.write_bytes(path.read_bytes()+b'changed')
    with pytest.raises(ValueError, match='hash mismatch'):
        load_snapshot(directory)


def test_failed_actual_collection_never_publishes_latest(tmp_path, monkeypatch):
    class FailingSource:
        def __init__(self, env_file):
            pass
        def pages(self, path, params):
            raise RuntimeError('test feed unavailable')
            yield
        def close(self):
            pass
    monkeypatch.setattr('quantcore.data.providers.alpaca.AlpacaData', FailingSource)
    target = tmp_path/'datasets/real_equities'
    with pytest.raises(RuntimeError):
        collect_snapshot(target, None, as_of='2026-11-25T01:30:00Z')
    assert not (target/'latest.json').exists()
    failure = next(target.glob('*/failure.json'))
    assert json.loads(failure.read_text())['status'] == 'failed'
    with pytest.raises(FileNotFoundError):
        latest_snapshot(tmp_path)
