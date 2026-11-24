import asyncio

import pytest

from quantcore.research.service import ResearchService


@pytest.fixture(scope='session')
def service(tmp_path_factory):
    result = ResearchService(tmp_path_factory.mktemp('data'))
    asyncio.run(result.bootstrap())
    yield result
    result.store.engine.dispose()


@pytest.fixture
def frame(service):
    return service.frames['QALPHA'].copy()


@pytest.fixture
def flat_frame(frame):
    result = frame.iloc[:100].copy()
    result[['open', 'close']] = 100.
    result['high'], result['low'], result['volume'] = 101., 99., 100000
    return result
