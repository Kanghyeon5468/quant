import asyncio

from quantcore.backtesting.engine import backtest
from quantcore.strategies.base import Momentum


def test_identical_inputs_identical_backtest(frame):
    assert backtest(frame, Momentum()) == backtest(frame, Momentum())


def test_reingestion_does_not_change_dataset(service):
    from quantcore.data.ingestion.pipeline import ingest
    from quantcore.data.providers.demo import DemoProvider
    outcome = asyncio.run(ingest(DemoProvider(), service.store))
    assert sum(outcome['inserted'].values()) == 0
    assert service.store.export_parquet()['sha256'] == service.version+service.manifest['sha256'][12:]
