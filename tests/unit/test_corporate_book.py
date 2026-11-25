from decimal import Decimal

import pandas as pd
import pytest

from quantcore.accounting.corporate import dividend_reconciliation, event_book
from quantcore.data.reference.securities import normalize_actions

UTC = '2026-11-25T20:00:00Z'


def fill(symbol, qty, price, at, side='buy'):
    return {'symbol':symbol,'qty':qty,'price':price,'timestamp':at,'side':side}


def event(kind='split', **kwargs):
    return {'id':'event-1','type':kind,'symbol':'ABC','ratio':'2','available_at':'2026-11-20T12:00:00Z',
            'effective_at':'2026-11-24T14:30:00Z', **kwargs}


def test_split_cost_and_post_split_sale_reconcile_without_artificial_profit():
    fills = [fill('ABC',10,100,'2026-11-23T15:00:00Z'),fill('ABC',5,60,'2026-11-25T15:00:00Z','sell')]
    book = event_book(fills,[event()],UTC)
    assert book['inventory']['ABC'] == 15 and book['basis']['ABC'] == 750
    assert book['realized_gross'] == 50 and book['quantity_adjustments']['ABC'] == 10
    assert book['trade_cash']+book['inventory']['ABC']*60 == 200
    assert not book['issues']


def test_reverse_split_preserves_basis_and_fractional_cash_in_lieu_is_not_invented():
    fills = [fill('ABC',8,100,'2026-11-23T15:00:00Z')]
    book = event_book(fills,[event(ratio='.5')],UTC)
    assert book['inventory']['ABC'] == 4 and book['basis']['ABC'] == 800
    fractional = event_book(fills,[event(ratio='.3')],UTC)
    assert fractional['inventory']['ABC'] == Decimal('2.4') and fractional['issues']
    assert fractional['trade_cash'] == -800


def test_dividend_ex_rights_exclude_same_open_buys_and_require_actual_cash_posting():
    fills = [fill('ABC',10,100,'2026-11-23T15:00:00Z'),fill('ABC',2,100,'2026-11-24T14:30:00Z')]
    book = event_book(fills,[event('dividend',rate='1',payable_date='2026-11-27',currency='USD')],UTC)
    assert book['dividend_claims'][0]['eligible_qty'] == '10'
    assert book['dividend_claims'][0]['expected_gross'] == '10'
    assert book['trade_cash'] == -1200 and book['realized_gross'] == 0
    pending = dividend_reconciliation(book['dividend_claims'],[],UTC)
    assert pending[0]['status'] == 'pending_payment'
    absent = dividend_reconciliation(book['dividend_claims'],[],'2026-11-28T18:00:00Z')
    assert absent[0]['status'] == 'not_credited_in_paper'
    activities = [{'activity_type':'DIV','symbol':'ABC','date':'2026-11-27','net_amount':'10'},
                  {'activity_type':'DIVNRA','symbol':'ABC','date':'2026-11-27','net_amount':'-1.5'}]
    posted = dividend_reconciliation(book['dividend_claims'],activities,'2026-11-28T18:00:00Z')
    assert posted[0]['status'] == 'broker_posted' and posted[0]['broker_net_received'] == '8.5'
    assert posted[0]['cash_credit_created_by_system'] == '0'


def test_symbol_change_transfers_quantity_and_cost_to_new_symbol():
    fills = [fill('ABC',10,100,'2026-11-23T15:00:00Z'),fill('XYZ',3,130,'2026-11-25T15:00:00Z','sell')]
    book = event_book(fills,[event('rename',new_symbol='XYZ')],UTC)
    assert book['inventory']['ABC'] == 0 and book['inventory']['XYZ'] == 7
    assert book['basis']['XYZ'] == 700 and book['realized_gross'] == 90
    assert book['quantity_adjustments'] == {'ABC':-10,'XYZ':10}


def test_events_cannot_change_book_before_their_available_time():
    fills = [fill('ABC',10,100,'2026-11-23T15:00:00Z')]
    future = event(available_at='2026-11-26T00:00:00Z')
    book = event_book(fills,[future],UTC)
    assert book['inventory']['ABC'] == 10 and not book['quantity_adjustments']
    with pytest.raises(ValueError,match='duplicate'):
        event_book(fills,[event(),event()],UTC)
    with pytest.raises(ValueError,match='future fill'):
        event_book(fills,[],pd.Timestamp('2026-11-20',tz='UTC'))


def test_normalization_retains_source_receipt_time_not_process_date_as_public_time():
    payload = {'forward_splits':[{'id':'s','symbol':'ABC','old_rate':1,'new_rate':2,'ex_date':'2026-11-24'}],
               'name_changes':[{'id':'n','old_symbol':'ABC','new_symbol':'XYZ','process_date':'2026-11-25'}]}
    rows = normalize_actions(payload,'2026-11-26T12:00:00Z')
    assert rows[0]['available_at'] == '2026-11-26T12:00:00Z' and rows[0]['public_at'] is None
    assert rows[1]['new_symbol'] == 'XYZ'
    payload['forward_splits'][0]['old_rate'] = 0
    with pytest.raises(ValueError):
        normalize_actions(payload,UTC)
