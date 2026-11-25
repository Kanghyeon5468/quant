from decimal import Decimal

import httpx
import numpy as np
import pandas as pd
import pytest

pytest.importorskip('exchange_calendars')
pytest.importorskip('dotenv')

from quantcore.backtesting.engine import CorporateAction, ExecutionConfig, backtest, simulate
from quantcore.data.calendar import action_open, sessions
from quantcore.data.providers.alpaca import (
    SYMBOLS,
    AlpacaData,
    corporate_actions,
    load_snapshot,
    regular_daily,
)
from quantcore.research.real_equities import ledger_audit
from quantcore.strategies.base import BuyHold, Momentum


def no_cost():
    return ExecutionConfig(commission_bps=0, slippage_bps=0, spread_bps=0, impact_bps=0)


def historic(flat_frame):
    frame = flat_frame.copy()
    schedule = sessions('2025-01-02', '2025-06-30').iloc[:len(frame)]
    frame.index = pd.DatetimeIndex(schedule['close'], name='timestamp')
    frame['available_at'] = frame.index+pd.Timedelta(minutes=1)
    frame['execution_open'] = list(schedule['open'])
    frame['signal_close'] = frame.close
    frame['mode'] = 'historical'
    return frame


def test_exchange_calendar_holiday_dst_and_early_close():
    spring = sessions('2026-03-06', '2026-03-09')
    assert spring.iloc[0]['open'].hour == 14
    assert spring.iloc[1]['open'].hour == 13
    assert '2026-07-03' not in sessions('2026-07-01', '2026-07-07').index
    assert sessions('2026-11-27', '2026-11-27').iloc[0]['close'].hour == 18
    assert len(sessions('2026-11-23', '2026-11-24', '2026-11-24T20:00:00Z')) == 1
    with pytest.raises(ValueError):
        sessions('2026-11-23', '2026-11-24', '2026-11-24')


def test_historical_exact_clock_and_no_synthetic_fallback(flat_frame):
    frame = historic(flat_frame)
    result = simulate(frame, BuyHold(), no_cost())
    assert result['mode'] == 'historical'
    assert pd.Timestamp(result['fills'][0]['timestamp']) == frame.iloc[1].execution_open
    assert result['metrics']['total_return'] == 0
    assert ledger_audit(frame, result)
    with pytest.raises(ValueError, match='requires actual session'):
        simulate(frame.drop(columns='execution_open'), BuyHold())


def test_dividend_receivable_is_not_spendable_until_payment(flat_frame):
    frame = historic(flat_frame)
    ex = frame.iloc[40].execution_open
    paid = frame.iloc[45].execution_open
    frame.loc[frame.index[40]:, ['open', 'close', 'signal_close']] = 99.
    result = simulate(frame, BuyHold(), no_cost(), [CorporateAction(ex, 'dividend', 1, paid)])
    curves = pd.DataFrame(result['curve']).set_index('timestamp')
    before = curves.loc[frame.index[39].isoformat()]
    ex_row = curves.loc[frame.index[40].isoformat()]
    assert Decimal(ex_row.dividend_receivable) == 950
    assert Decimal(ex_row.dividend_cash_paid) == 0
    assert float(ex_row.equity) == pytest.approx(float(before.equity))
    payment_row = curves.loc[frame.index[45].isoformat()]
    assert Decimal(payment_row.dividend_receivable) == 0
    assert Decimal(payment_row.dividend_cash_paid) == 950
    with pytest.raises(ValueError, match='cash availability'):
        simulate(frame, BuyHold(), no_cost(), [CorporateAction(ex, 'dividend', 1)])


def test_no_dividend_entitlement_for_ex_day_purchase(flat_frame):
    frame = historic(flat_frame)
    event = CorporateAction(frame.iloc[1].execution_open, 'dividend', 1, frame.iloc[4].execution_open)
    result = simulate(frame, BuyHold(), no_cost(), [event])
    assert all(Decimal(r['dividend_cash_paid']) == 0 for r in result['curve'])


def test_split_cash_inventory_and_causal_signal(flat_frame):
    frame = historic(flat_frame)
    ex = frame.iloc[50].execution_open
    frame.loc[frame.index[50]:, ['open', 'close']] /= 2
    frame['signal_close'] = 100.
    result = simulate(frame, BuyHold(), no_cost(), [CorporateAction(ex, 'split', 2)])
    assert result['curve'][-1]['equity'] == 100000
    assert result['curve'][-1]['quantity'] == 1900
    # Split-adjusted signals are used; a raw artificial price drop cannot enter the signal.
    with_signal = backtest(frame, Momentum(), no_cost(), [CorporateAction(ex, 'split', 2)])
    assert with_signal['fills'] == []


def test_corporate_action_payment_mapping_and_unknowns():
    row = {'symbol': 'AAPL', 'id': 'test-dividend', 'ex_date': '2026-11-20',
           'payable_date': '2026-11-26', 'rate': .25, 'foreign': False}
    payload = {'cash_dividends': [row, row]}
    actions = corporate_actions(payload, '2026-11-01', '2026-11-24')['AAPL']
    assert len(actions) == 1
    assert actions[0].payable_at == action_open('2026-11-27')
    assert corporate_actions(payload, '2026-11-21', '2026-11-24')['AAPL'] == []
    with pytest.raises(ValueError, match='unsupported'):
        corporate_actions({'spin_offs': [row]}, '2026-11-01', '2026-11-24')
    with pytest.raises(ValueError, match='currency'):
        corporate_actions({'cash_dividends': [{**row, 'currency': 'EUR'}]}, '2026-11-01', '2026-11-24')
    with pytest.raises(ValueError, match='not an exchange session'):
        corporate_actions({'cash_dividends': [{**row, 'ex_date': '2026-11-21'}]}, '2026-11-01', '2026-11-24')


def test_split_participation_and_impact_use_current_share_units(flat_frame):
    frame = historic(flat_frame)
    ex = frame.iloc[1].execution_open
    frame.loc[frame.index[1]:, ['open', 'close']] = 50.
    config = no_cost().model_copy(update={'impact_bps': 5})
    result = simulate(frame, BuyHold(), config, [CorporateAction(ex, 'split', 2)])
    first = result['fills'][0]
    assert first['quantity'] == 1900
    expected = 50*(1+5*np.sqrt(1900/200000)/10000)
    assert first['price'] == pytest.approx(expected, abs=1e-12)


def minute_fixture():
    schedule = sessions('2026-06-08', '2026-06-09')
    rows = []
    for symbol in SYMBOLS:
        for day, clock in schedule.iterrows():
            price = 100. if day == '2026-06-08' else 50.
            for stamp in [clock['open']-pd.Timedelta(minutes=1), clock['open'], clock['close']-pd.Timedelta(minutes=1)]:
                rows.append({'symbol': symbol, 't': stamp.isoformat(), 'o': price, 'h': price+1,
                             'l': price-1, 'c': price, 'v': 1000})
    return pd.DataFrame(rows), schedule


def test_regular_session_aggregation_and_forward_split_index():
    minutes, schedule = minute_fixture()
    actions = {symbol: [CorporateAction(schedule.iloc[1]['open'], 'split', 2)] for symbol in SYMBOLS}
    daily, count = regular_daily(minutes, schedule, actions)
    assert count == 20 and len(daily) == 10
    assert (daily.volume == 2000).all()  # Premarket 1-minute rows excluded.
    assert (daily.signal_close == 100).all()
    for symbol in SYMBOLS:
        assert daily[daily.symbol == symbol].iloc[0].signal_close == 100
    altered = {symbol: actions[symbol]+[CorporateAction(pd.Timestamp('2026-07-01T13:30:00Z'), 'split', 10)] for symbol in SYMBOLS}
    future_changed, _ = regular_daily(minutes, schedule, altered)
    np.testing.assert_array_equal(daily.signal_close, future_changed.signal_close)
    with pytest.raises(ValueError, match='duplicate'):
        regular_daily(pd.concat([minutes, minutes.iloc[:1]]), schedule, actions)
    with pytest.raises(ValueError, match='missing exchange sessions'):
        regular_daily(minutes[minutes.symbol != 'SPY'], schedule, actions)


def test_market_data_client_only_get_and_pagination(tmp_path, monkeypatch):
    monkeypatch.setattr('quantcore.data.providers.alpaca.time.sleep', lambda seconds: None)
    key = tmp_path/'credentials.env'
    key.write_text('ALPACA_API_KEY=test-key\nALPACA_SECRET_KEY=test-secret\n')
    seen = []
    def handler(request):
        seen.append(request)
        assert request.method == 'GET' and request.url.host == 'data.alpaca.markets'
        assert request.headers['APCA-API-KEY-ID'] == 'test-key'
        return httpx.Response(200, json={'bars': {}, 'next_page_token': 'next' if len(seen) == 1 else None})
    client = AlpacaData(key, httpx.MockTransport(handler))
    assert len(list(client.pages('/v2/stocks/bars', {}))) == 2
    with pytest.raises(ValueError, match='authorized'):
        list(client.pages('/v2/orders', {}))
    client.close()
    rejected = AlpacaData(key, httpx.MockTransport(lambda request: httpx.Response(403)))
    with pytest.raises(RuntimeError, match='HTTP 403'):
        list(rejected.pages('/v2/stocks/bars', {}))
    rejected.close()
    with pytest.raises(ValueError, match='credentials missing'):
        AlpacaData(tmp_path/'absent.env')
    (tmp_path/'manifest.json').write_text('{"status":"failed"}')
    with pytest.raises(ValueError):
        load_snapshot(tmp_path)
