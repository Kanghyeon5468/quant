import asyncio

import numpy as np
import pytest

from quantcore.core.models import Event
from quantcore.events.bus import EventBus
from quantcore.incremental.graph import Graph, RollingStats


def graph():
    g = Graph()
    g.input('a', 2.)
    g.input('b', 3.)
    g.derive('square', ['a'], lambda a: a*a)
    g.derive('total', ['square', 'b'], lambda a, b: a+b)
    g.stabilize()
    return g


def test_affected_nodes_and_cache():
    g = graph()
    before = g.computations
    changes = []
    g.listeners.append(changes.append)
    g.update({'b': 5.})
    assert g.get('total') == 9.
    assert g.computations-before == 1
    assert changes[-1] == ('total',)
    g.update({'b': 5.})
    assert g.cache_hits == 1
    assert g.nodes['b'].version == 1
    assert g.topological().index('square') < g.topological().index('total')


def test_cycles_and_invalid_updates():
    g = graph()
    with pytest.raises(ValueError):
        g.dependencies('square', ['total'])
    with pytest.raises(ValueError):
        g.derive('loop', ['loop'], lambda x: x)
    with pytest.raises(ValueError):
        g.input('a', 0)
    with pytest.raises(ValueError):
        g.derive('x', ['unknown'], lambda x: x)
    with pytest.raises(ValueError):
        g.update({'square': 5})
    with pytest.raises(ValueError):
        g.dependencies('square', ['unknown'])
    g.dependencies('total', ['a', 'b'])
    g.stabilize()
    assert g.get('total') == 5.


def test_computation_failure_stays_dirty():
    g = Graph()
    g.input('a', 1.)
    g.derive('inverse', ['a'], lambda a: 1/a)
    g.stabilize()
    with pytest.raises(ZeroDivisionError):
        g.update({'a': 0.})
    with pytest.raises(RuntimeError):
        g.get('inverse')
    g.update({'a': 2.})
    assert g.get('inverse') == .5


def test_rolling_vs_batch():
    r = RollingStats(20)
    values = np.random.default_rng(4).normal(0, 1, 100)
    for i, value in enumerate(values):
        mean, variance = r.append(float(value))
        expected = values[max(0, i-19):i+1]
        assert mean == pytest.approx(expected.mean(), abs=1e-12)
        assert variance == pytest.approx(expected.var(ddof=1) if len(expected) > 1 else 0, abs=1e-12)
    with pytest.raises(ValueError):
        RollingStats(1)
    with pytest.raises(ValueError):
        r.append(float('nan'))


def test_bus_isolates_failure():
    async def scenario():
        bus = EventBus(2)
        seen = []
        async def bad(event):
            raise ValueError('broken consumer')
        async def good(event):
            seen.append(event.version)
        bus.subscribe('price', bad)
        bus.subscribe('price', good)
        await bus.publish(Event(kind='price', version=1, timestamp='2025-01-01T00:00:00Z'))
        await bus.drain()
        assert seen == [1] and len(bus.failures) == 1 and bus.queue.qsize() == 0
    asyncio.run(scenario())
