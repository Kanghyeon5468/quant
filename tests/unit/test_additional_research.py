from datetime import datetime, timezone

import pytest

from quantcore.macro.vintages import Observation, available_vintages
from quantcore.statistics.research import benjamini_hochberg, statistical_report


def test_multiple_testing_and_statistics(service):
    assert benjamini_hochberg([.01, .04, .03]) == pytest.approx([.03, .04, .04])
    with pytest.raises(ValueError):
        benjamini_hochberg([2.])
    result = statistical_report(service.returns())
    assert sum(result['pca_explained_variance_ratio']) == pytest.approx(1.)
    assert result['bootstrap']['samples'] == 1000
    with pytest.raises(ValueError):
        statistical_report(service.returns().iloc[:10])


def test_macro_vintage_does_not_leak_revisions():
    original = Observation(series='SYNTHETIC_CPI', period='2025-01-01', value=100,
        released_at='2025-02-01T00:00:00Z', collected_at='2025-02-01T01:00:00Z', source='synthetic', unit='index')
    revision = original.model_copy(update={'value': 105, 'released_at': datetime(2025, 3, 1, tzinfo=timezone.utc),
                                          'collected_at': datetime(2025, 3, 1, 1, tzinfo=timezone.utc)})
    before = available_vintages([original, revision], datetime(2025, 2, 15, tzinfo=timezone.utc))
    after = available_vintages([original, revision], datetime(2025, 3, 2, tzinfo=timezone.utc))
    assert before[0].value == 100 and after[0].value == 105
    with pytest.raises(ValueError):
        available_vintages([original], datetime(2025, 2, 15))
    with pytest.raises(ValueError):
        Observation(**{**original.model_dump(), 'collected_at': '2025-01-01T00:00:00Z'})
    with pytest.raises(ValueError):
        Observation(**{**original.model_dump(), 'released_at': '2025-01-01'})


def test_amended_financial_periods_keep_prior_period(service):
    symbol = 'QBETA'
    original = service.store.fundamentals(symbol, service.as_of)[-1]
    amendment = {**original, 'available_at': '2027-01-01T00:00:00Z', 'published_at': '2027-01-01T00:00:00Z',
                 'revenue': original['revenue']*2}
    service.store.save_fundamentals([amendment])
    before = service.store.fundamentals(symbol, service.as_of)
    after = service.store.fundamentals(symbol, '2027-02-01T00:00:00Z')
    assert len(before) == len(after) == 3
    assert before[-1]['revenue']*2 == after[-1]['revenue']
    assert before[-2] == after[-2]
