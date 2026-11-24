import asyncio
from collections.abc import Awaitable, Callable
from typing import Protocol

from quantcore.core.models import Asset, Bar


class Provider(Protocol):
    def assets(self) -> list[Asset]: ...
    async def fetch(self, symbol: str) -> list[Bar]: ...


class RateLimiter:
    def __init__(self, interval=.01):
        if interval < 0:
            raise ValueError('negative interval')
        self.interval = interval
        self.lock = asyncio.Lock()
        self.next_at = 0.

    async def wait(self):
        async with self.lock:
            loop = asyncio.get_running_loop()
            await asyncio.sleep(max(0, self.next_at-loop.time()))
            self.next_at = loop.time()+self.interval


async def retry(operation: Callable[[], Awaitable], attempts=3, base_delay=.05):
    if attempts < 1:
        raise ValueError('attempts must be positive')
    for attempt in range(attempts):
        try:
            return await operation()
        except (TimeoutError, ConnectionError):
            if attempt+1 == attempts:
                raise
            await asyncio.sleep(base_delay*2**attempt)


async def ingest(provider: Provider, store):
    limiter = RateLimiter()
    semaphore = asyncio.Semaphore(3)

    async def collect(asset):
        async with semaphore:
            await limiter.wait()
            bars = await retry(lambda: provider.fetch(asset.symbol))
            if any(bar.symbol != asset.symbol or bar.currency != asset.currency for bar in bars):
                raise ValueError('asset attribution/currency mismatch')
            return asset, bars

    outcomes = await asyncio.gather(*(collect(a) for a in provider.assets()), return_exceptions=True)
    counts, errors = {}, []
    for result in outcomes:
        if isinstance(result, BaseException):
            errors.append(type(result).__name__)
        else:
            asset, bars = result
            store.save_asset(asset)
            counts[asset.symbol] = store.save_bars(bars)
    store.audit('ingestion', {'inserted': counts, 'errors': errors})
    return {'inserted': counts, 'errors': errors}
