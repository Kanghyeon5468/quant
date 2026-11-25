from decimal import Decimal
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from quantcore.backtesting.portfolio import match_limit, replay
from quantcore.data.calendar import sessions
from quantcore.risk.limits import RiskLimits, account_state, features, filter_orders
from quantcore.strategies.orders import OrderPolicy, slot_orders


def market():
    schedule = sessions('2026-07-01', '2026-11-24')
    rows, minutes = [], []
    for s in ['AAPL', 'MSFT']:
        for i, (day, clock) in enumerate(schedule.iterrows()):
            price = 100+i*.1
            rows.append({'symbol': s, 'session': day, 'timestamp': clock['close'],
                         'available_at': clock['close']+pd.Timedelta(minutes=1), 'close': price,
                         'signal_close': price, 'volume': 10000})
            minutes.append({'symbol': s, 'session': day, 'timestamp': clock['open'],
                            'o': price, 'h': price+1, 'l': price-1, 'c': price, 'v': 10000})
    return pd.DataFrame(rows), pd.DataFrame(minutes)


def setup_risk():
    daily, _ = market()
    histories = {s: f for s, f in daily.groupby('symbol')}
    feature = features(histories, pd.Timestamp('2026-11-25', tz='UTC'))
    return feature, histories


def order(symbol='AAPL', qty='500', side='buy', price='100'):
    return {'symbol': symbol, 'qty': qty, 'side': side, 'limit_price': price}


def check(limits=None, **kw):
    f, _ = setup_risk()
    args = dict(feature=f, inventory={'AAPL': 0, 'MSFT': 0}, marks={'AAPL': 100, 'MSFT': 100},
                pending=[], orders=[order()], equity=100000, daily_start=100000, peak=100000,
                limits=limits or RiskLimits())
    args.update(kw)
    return filter_orders(**args)


def test_liquidity_position_sector_correlation_and_volatility_limits():
    assert check()['orders'][0]['qty'] == '100'  # ADV20 * 1%
    relaxed = RiskLimits(adv_participation=1)
    assert check(relaxed)['orders'][0]['qty'] == '200'
    r = check(relaxed, orders=[order('AAPL', '200'), order('MSFT', '500')])
    assert int(r['orders'][1]['qty']) <= 200
    assert 'position_weight' in r['rejected'][0]['rules']
    assert check(RiskLimits(adv_participation=1, sector_weight=.1))['orders'][0]['qty'] == '100'
    assert check(RiskLimits(adv_participation=1, correlated_weight=.1))['orders'][0]['qty'] == '100'
    f, _ = setup_risk()
    f['covariance'] = [[4, 0], [0, 4]]
    result = check(RiskLimits(adv_participation=1), feature=f)
    assert result['orders'][0]['qty'] == '125'
    assert 'portfolio_volatility' in result['rejected'][0]['rules']


def test_halts_cancel_only_buys_and_keep_owned_exits():
    pending = [{**order(qty='10'), 'remaining_qty': '10', 'client_order_id': 'own-buy'},
               {**order(qty='10', side='sell'), 'remaining_qty': '10', 'client_order_id': 'own-sell'}]
    r = check(equity=97000, pending=pending, inventory={'AAPL': 10, 'MSFT': 0},
              orders=[order(), order(qty='10', side='sell')])
    assert r['halt_rules'] == ['daily_loss']
    assert [o['client_order_id'] for o in r['cancel_pending']] == ['own-buy']
    assert [o['side'] for o in r['orders']] == ['sell']
    with pytest.raises(ValueError, match='exceeds'):
        check(orders=[order(side='sell')])


def test_persistent_day_and_drawdown_latches_and_budget_adjustment():
    initial = account_state({}, 100000, 100000, 5000, '2026-11-24', 'a')
    initial.update(daily_latched=True, drawdown_latched=True)
    changed = account_state(initial, 100000, 100000, 100000, '2026-11-24', 'a')
    assert changed['peak'] == changed['daily_start'] == 100000
    assert changed['daily_latched']
    tomorrow = account_state(changed, 100000, 100000, 100000, '2026-11-25', 'a')
    assert not tomorrow['daily_latched'] and tomorrow['drawdown_latched']
    assert check(drawdown_latched=True)['halt_rules'] == ['drawdown']
    with pytest.raises(ValueError, match='different account'):
        account_state(changed, 100000, 100000, 100000, '2026-11-25', 'b')


def test_feature_cutoff_blocks_future_information_and_missing_data():
    _, histories = setup_risk()
    cut = histories['AAPL'].available_at.iloc[-4]
    before = features(histories, cut)
    changed = {s: f.copy() for s, f in histories.items()}
    for f in changed.values():
        f.loc[f.available_at > cut, ['close', 'signal_close']] *= 100
    assert features(changed, cut) == before
    with pytest.raises(ValueError, match='60 available'):
        features({s: f.head(59) for s, f in histories.items()}, cut)


def test_limit_matching_partial_volume_and_fee_reservation():
    o = {**order(qty='100', price='101'), 'reference': 100, 'remaining': 100}
    bar = SimpleNamespace(o=100, h=102, l=99, c=100, v=200)
    fill = match_limit(o, bar, OrderPolicy(), 10000, Decimal(100000), 0)
    assert fill[0] == 2 and Decimal(100) < fill[1] <= Decimal(101)
    bar.l = 102
    assert match_limit(o, bar, OrderPolicy(), 10000, Decimal(100000), 0) is None
    bar.l = 99
    assert match_limit(o, bar, OrderPolicy(), 10000, Decimal(1), 0) is None
    sell = {**o, 'side': 'sell', 'limit_price': '99'}
    assert match_limit(sell, bar, OrderPolicy(), 10000, Decimal(0), 1)[0] == 1


def test_single_cash_replay_is_causal_and_reconciles():
    daily, minutes = market()
    result = replay(daily, minutes, evaluation_sessions=5, risk_enabled=False)
    assert result['metrics']['expired_orders'] > 0
    assert result['audit']['signal_before_fill'] and result['audit']['limit_respected']
    assert Decimal(result['audit']['min_cash']) >= 0
    quantities = dict.fromkeys(['AAPL', 'MSFT'], 0)
    cash = Decimal(100000)
    for row in result['curve']:
        for f in [f for f in result['fills'] if f['session'] == row['session']]:
            signed = f['quantity']*(1 if f['side'] == 'buy' else -1)
            cash -= (1 if signed > 0 else -1)*Decimal(f['notional'])+Decimal(f['commission'])
            quantities[f['symbol']] += signed
        assert row['holdings'] == quantities and Decimal(row['cash']) == cash
        marks = daily[daily.session == row['session']].set_index('symbol').close
        assert np.isclose(row['equity'], float(cash)+sum(q*marks[s] for s, q in quantities.items()))
    cut = minutes[minutes.session == sorted(minutes.session.unique())[-2]].timestamp.min()
    altered = minutes.copy()
    altered.loc[altered.timestamp >= cut, ['o', 'h', 'l', 'c']] *= 1.2
    mutated = daily.copy()
    mutated.loc[mutated.session >= str(cut.date()), ['close', 'signal_close']] *= 1.2
    future = replay(mutated, altered, evaluation_sessions=5, risk_enabled=False)
    def prefix(r):
        return [f for f in r['fills'] if pd.Timestamp(f['timestamp']) < cut]
    assert prefix(result) == prefix(future)
    histories = {s: f[f.session < result['curve'][0]['session']] for s, f in daily.groupby('symbol')}
    planned = slot_orders(histories, dict.fromkeys(histories, 0), 100000, 100000, 'momentum')['orders']
    assert [(o['symbol'], o['qty'], o['limit_price']) for o in planned] == [
        (o['symbol'], o['qty'], o['limit_price']) for o in result['orders'] if o['session'] == result['curve'][0]['session']]


def test_policy_hash_matches_reloaded_defaults():
    for model in (OrderPolicy, RiskLimits):
        original = model()
        assert model.model_validate_json(original.model_dump_json()).version == original.version


def test_drawdown_reset_requires_pause_and_reason_and_preserves_daily_halt(tmp_path):
    import json

    from quantcore.paper.guard import reset_drawdown
    from quantcore.paper.runner import Journal
    journal = Journal(tmp_path)
    journal.db.execute('CREATE TABLE risk_state (id INTEGER PRIMARY KEY, data TEXT)')
    journal.db.execute('INSERT INTO risk_state VALUES (1, ?)', (json.dumps({
        'last_equity': 90000, 'peak': 100000, 'daily_latched': True, 'drawdown_latched': True}),))
    journal.db.commit()
    with pytest.raises(ValueError, match='pause'):
        reset_drawdown(journal, 'reviewed')
    (tmp_path/'STOP').touch()
    with pytest.raises(ValueError, match='reason'):
        reset_drawdown(journal, '')
    reset = reset_drawdown(journal, 'reviewed after strategy change')
    assert reset == {'peak': 90000, 'drawdown_latched': False, 'daily_latched': True}
    assert journal.db.execute('SELECT COUNT(*) FROM risk_resets').fetchone()[0] == 1
    journal.close()


def test_intraday_drawdown_cancels_rest_and_latches_without_forced_sale():
    daily, minutes = market()
    days = sorted(daily.session.unique())[-5:]
    extra = minutes[minutes.session.isin(days)].copy()
    extra['timestamp'] += pd.Timedelta(minutes=4)
    extra['v'] = 100
    first = extra.session == days[0]
    extra.loc[first, ['o', 'h', 'l', 'c']] *= .5
    daily.loc[daily.session == days[0], ['close', 'signal_close']] *= .5
    minutes = pd.concat([minutes, extra]).sort_values('timestamp')
    result = replay(daily, minutes, evaluation_sessions=5, limits=RiskLimits(adv_participation=.1))
    assert result['metrics']['risk_canceled_orders'] > 0
    assert any(e['rule'] == 'drawdown' for e in result['risk_events'])
    assert result['curve'][-1]['drawdown_latched']
    assert not any(f['side'] == 'sell' for f in result['fills'] if f['session'] == days[0])
    assert result['audit']['cash_inventory_nav_reconciled']


def test_strategy_changes_keep_one_cash_book_and_cannot_change_earlier_fills():
    daily,minutes=market()
    days=sorted(daily.session.unique())[-5:]
    constant=dict.fromkeys(days,'momentum')
    changed={**constant,**dict.fromkeys(days[-2:],'mean_reversion')}
    baseline=replay(daily,minutes,evaluation_sessions=5,risk_enabled=False,strategy_by_day=constant)
    selected=replay(daily,minutes,evaluation_sessions=5,risk_enabled=False,strategy_by_day=changed)
    assert selected['curve'][:3]==baseline['curve'][:3]
    assert [f for f in selected['fills'] if f['session']<days[-2]]==[f for f in baseline['fills'] if f['session']<days[-2]]
    assert selected['curve'][3]['strategy']=='mean_reversion'
    assert Decimal(selected['curve'][3]['cash'])>Decimal(selected['curve'][2]['cash'])
    assert selected['curve'][-1]['holdings']!=baseline['curve'][-1]['holdings']
    assert selected['audit']['cash_inventory_nav_reconciled']
