import asyncio
from datetime import datetime

import pytest

from quantcore.core.models import Bar
from quantcore.data.ingestion.pipeline import RateLimiter, ingest, retry
from quantcore.data.providers.demo import DemoProvider
from quantcore.data.storage.store import Store
from quantcore.data.validation.quality import quality_report


def sample():
    return asyncio.run(DemoProvider(periods=3).fetch('QALPHA'))[0]


@pytest.mark.parametrize('change', [dict(close=-1), dict(high=1), dict(low=1e9), dict(volume=-1),
    dict(close=float('nan')), dict(open=float('inf')), dict(currency='EUR'), dict(timestamp=datetime(2025, 1, 1)),
    dict(available_at='2000-01-01T00:00:00Z'), dict(extra='unexpected')])
def test_invalid_bar(change):
    with pytest.raises(ValueError):
        Bar.model_validate({**sample().model_dump(), **change})


def test_utc_normalization():
    bar = sample()
    changed = Bar.model_validate({**bar.model_dump(), 'timestamp': '2023-01-03T06:00:00+09:00',
                                  'available_at': '2023-01-03T06:00:00+09:00'})
    assert changed.timestamp.isoformat() == '2023-01-02T21:00:00+00:00'


def test_deterministic_provider():
    a = asyncio.run(DemoProvider().fetch('QALPHA'))
    b = asyncio.run(DemoProvider().fetch('QALPHA'))
    assert a == b
    with pytest.raises(ValueError):
        asyncio.run(DemoProvider().fetch('UNKNOWN'))


def test_storage_idempotence_conflicts_and_transaction(tmp_path):
    store = Store(tmp_path)
    rows = asyncio.run(DemoProvider(periods=3).fetch('QALPHA'))
    assert store.save_bars(rows) == 3
    assert store.save_bars(rows) == 0
    changed = rows[0].model_copy(update={'volume': 1})
    with pytest.raises(ValueError, match='immutable'):
        store.save_bars([changed])
    assert len(store.prices('QALPHA')) == 3
    assert store.prices("QALPHA' OR 1=1 --").empty
    assert len(store.prices('QALPHA', rows[1].available_at)) == 2
    with pytest.raises(ValueError):
        store.prices('QALPHA', '2023-01-01')
    store.engine.dispose()


def test_facts_point_in_time(service):
    assert service.store.fundamentals('QALPHA', '2023-02-14T21:00:00Z') == []
    assert len(service.store.fundamentals('QALPHA', '2023-02-15T21:00:00Z')) == 1
    with pytest.raises(ValueError):
        service.store.fundamentals('QALPHA', '2023-02-15')
    bad = DemoProvider().fundamentals()[0]
    with pytest.raises(ValueError):
        service.store.save_fundamentals([{**bad, 'unit': 'thousands'}])
    with pytest.raises(ValueError):
        service.store.save_fundamentals([{**bad, 'available_at': '2000-01-01T00:00:00Z'}])


def test_parquet_and_quality(service, frame):
    assert sum(r['rows'] for r in service.store.parquet_summary()) == 4680
    assert quality_report(frame)['score'] == 1
    assert quality_report(frame.iloc[0:0])['status'] == 'missing'
    damaged = frame.drop(frame.index[3])
    damaged.loc[damaged.index[4], 'close'] *= 3
    assert quality_report(damaged)['score'] < 1


def test_retry_and_limiter():
    async def scenario():
        attempts = []
        async def transient():
            attempts.append(1)
            if len(attempts) < 3:
                raise TimeoutError()
            return 42
        assert await retry(transient, base_delay=0) == 42
        async def failure():
            raise ConnectionError()
        with pytest.raises(ConnectionError):
            await retry(failure, attempts=2, base_delay=0)
        with pytest.raises(ValueError):
            await retry(failure, attempts=0)
        limiter = RateLimiter(0)
        await asyncio.gather(limiter.wait(), limiter.wait())
    asyncio.run(scenario())
    with pytest.raises(ValueError):
        RateLimiter(-1)


def test_provider_fault_isolation(tmp_path):
    class Broken(DemoProvider):
        async def fetch(self, symbol):
            if symbol == 'QALPHA':
                raise ValueError('bad feed')
            return await super().fetch(symbol)
    store = Store(tmp_path)
    outcome = asyncio.run(ingest(Broken(periods=3), store))
    assert len(outcome['inserted']) == 5 and outcome['errors'] == ['ValueError']
    store.engine.dispose()
