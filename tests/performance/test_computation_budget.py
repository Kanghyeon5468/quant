from quantcore.incremental.graph import Graph


def test_one_asset_change_recomputes_only_its_branch_and_portfolio():
    g = Graph()
    for i in range(100):
        g.input(f'price{i}', 100.)
        g.derive(f'value{i}', [f'price{i}'], lambda p: p*10)
    g.derive('portfolio', [f'value{i}' for i in range(100)], lambda *values: sum(values))
    g.stabilize()
    count = g.computations
    g.update({'price0': 101.})
    assert g.computations-count == 2
    assert g.get('portfolio') == 100010.
    g.update({'price0': 101.})
    assert g.computations-count == 2
