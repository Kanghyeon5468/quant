import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from quantcore.incremental.graph import Graph


@given(st.lists(st.floats(min_value=-100, max_value=100, allow_nan=False, allow_infinity=False), min_size=1, max_size=40))
@settings(max_examples=80, deadline=None, derandomize=True)
def test_incremental_equals_full_recomputation(values):
    g = Graph()
    g.input('price', 1.)
    g.input('other', 5.)
    g.derive('squared', ['price'], lambda p: p*p)
    g.derive('sum', ['squared', 'other'], lambda a, b: a+b)
    g.stabilize()
    for price in values:
        g.update({'price': price})
        incremental = g.get('sum')
        g.stabilize(full=True)
        assert g.get('sum') == pytest.approx(incremental, abs=1e-10)
        assert incremental == pytest.approx(price*price+5)


@given(st.floats(min_value=.01, max_value=.5, allow_nan=False, allow_infinity=False))
@settings(max_examples=30, derandomize=True)
def test_option_put_call_parity(volatility):
    from quantcore.derivatives.options import black_scholes
    call = black_scholes(100, 105, .75, .03, volatility)['price']
    put = black_scholes(100, 105, .75, .03, volatility, 'put')['price']
    assert call-put == pytest.approx(100-105*np.exp(-.03*.75), abs=1e-10)
