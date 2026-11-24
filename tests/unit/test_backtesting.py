from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from quantcore.backtesting.engine import CorporateAction, ExecutionConfig, backtest, simulate
from quantcore.machine_learning.validation import walk_forward
from quantcore.strategies.base import BuyHold, MeanReversion, Momentum


def no_cost(**values):
    return ExecutionConfig(commission_bps=0, slippage_bps=0, spread_bps=0, impact_bps=0, **values)


def test_known_flat_account(flat_frame):
    result = simulate(flat_frame, BuyHold(), no_cost())
    assert result['metrics']['total_return'] == 0
    assert result['curve'][-1]['quantity'] == 950
    assert Decimal(result['curve'][-1]['cash']) == 5000
    assert result['curve'][-1]['equity'] == 100000


def test_cash_inventory_and_execution_delay(frame):
    result = backtest(frame, Momentum())
    cash, inventory = Decimal(100000), 0
    for fill in result['fills']:
        direction = 1 if fill['side'] == 'buy' else -1
        cash -= direction*Decimal(str(fill['notional']))+Decimal(str(fill['commission']))
        inventory += direction*fill['quantity']
        assert cash == Decimal(fill['cash_after'])
        assert inventory == fill['inventory_after']
        assert cash >= 0 and inventory >= 0
        assert pd.Timestamp(fill['signal_at']) < pd.Timestamp(fill['timestamp'])
    assert result['metrics']['total_cost'] > 0
    assert result['gross_metrics']['total_return'] >= result['metrics']['total_return']
    assert len(result['curve']) == 252


def test_liquidity_partial_fills(flat_frame):
    flat_frame['volume'] = 100
    result = simulate(flat_frame, BuyHold(), no_cost())
    assert result['fills'][0]['quantity'] == 1
    assert result['fills'][0]['partial_fill']
    flat_frame['volume'] = 0
    assert simulate(flat_frame, BuyHold(), no_cost())['fills'] == []


def test_future_prices_do_not_change_past_fills(frame):
    original = simulate(frame, MeanReversion())
    altered = frame.copy()
    cutoff = frame.index[-30]
    altered.loc[cutoff:, ['open', 'high', 'low', 'close']] *= 2
    changed = simulate(altered, MeanReversion())
    def before(result):
        return [f for f in result['fills'] if pd.Timestamp(f['timestamp']) < cutoff-pd.Timedelta(hours=6, minutes=30)]
    assert before(original) == before(changed)


def test_actions_conserve_value_and_settle_delisting(flat_frame):
    f = flat_frame.copy()
    split_at = f.index[40]-pd.Timedelta(hours=6, minutes=30)
    f.loc[f.index[40]:, ['open', 'close']] /= 2
    result = simulate(f, BuyHold(), no_cost(), [CorporateAction(split_at, 'split', 2)])
    assert result['curve'][-1]['equity'] == 100000
    dividend = CorporateAction(f.index[50]-pd.Timedelta(hours=6, minutes=30), 'dividend', 1)
    result = simulate(flat_frame, BuyHold(), no_cost(), [dividend])
    assert result['curve'][-1]['equity'] > 100000
    delist = CorporateAction(f.index[60]-pd.Timedelta(hours=6, minutes=30), 'delisting', 0)
    result = simulate(flat_frame, BuyHold(), no_cost(), [delist])
    assert result['curve'][-1]['quantity'] == 0
    assert result['curve'][-1]['equity'] == 5000


@pytest.mark.parametrize('kind,value', [('unknown', 1), ('split', .333), ('dividend', -1)])
def test_invalid_actions(flat_frame, kind, value):
    action = CorporateAction(flat_frame.index[50], kind, value)
    with pytest.raises(ValueError):
        simulate(flat_frame, BuyHold(), no_cost(), [action])


def test_invalid_history_and_positions(frame):
    with pytest.raises(ValueError):
        simulate(frame.iloc[:2], BuyHold())
    with pytest.raises(ValueError):
        simulate(frame.iloc[::-1], BuyHold())
    invalid = frame.copy()
    invalid.iloc[1, invalid.columns.get_loc('close')] = np.nan
    with pytest.raises(ValueError):
        simulate(invalid, BuyHold())
    invalid = frame.copy()
    invalid.loc[invalid.index[-20], 'available_at'] = invalid.index[-19]
    with pytest.raises(ValueError, match='unavailable'):
        simulate(invalid, BuyHold())
    class Short:
        name = 'invalid'
        def targets(self, f):
            return pd.Series(-1., index=f.index)
    with pytest.raises(ValueError):
        simulate(frame, Short())


def test_ml_purge_and_baseline(frame):
    result = walk_forward(frame)
    assert {r['model'] for r in result['metrics']} == {'baseline_mean', 'ridge'}
    for split in result['splits']:
        assert pd.Timestamp(split['train_last_target']) < pd.Timestamp(split['test_start'])
    assert walk_forward(frame) == result
    with pytest.raises(ValueError):
        walk_forward(frame.iloc[:100])
    with pytest.raises(ValueError):
        walk_forward(frame, horizon=0)
