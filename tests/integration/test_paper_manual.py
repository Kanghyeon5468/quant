import json
from decimal import Decimal
from uuid import uuid4

import pandas as pd
import pytest

from quantcore.data.providers.alpaca import SYMBOLS
from quantcore.paper.client import PaperError
from quantcore.paper.journal import Journal
from quantcore.paper.manual import adopt_closures, authorized_reference, collect_references, rebalance
from quantcore.paper.performance import own_fill_ledger
from quantcore.paper.runner import cancel_own, make_plan, own_inventory, run_once
from tests.integration.test_paper_trading import setup_paper as existing_paper_fixture

setup_paper = existing_paper_fixture


def reference():
    return {'source':'alpaca-iex-regular-1min', 'session':'2026-11-25', 'collected_at':'2026-11-25T14:59:00Z',
        'references':{s:{'price':'112','bar_start':'2026-11-25T14:57:00Z','bar_end':'2026-11-25T14:58:00Z'} for s in SYMBOLS}}


def test_explicit_manual_request_reenters_once_without_changing_daily_time_guard(setup_paper, monkeypatch):
    client, broker, snapshot, directory, _, _ = setup_paper
    root = directory.parent
    directory = root/'artifacts/paper_trading'
    run_once(client, directory, snapshot, submit=True)
    cancel_own(client, directory)
    broker.clock.update(timestamp='2026-11-25T15:00:00Z', is_open=True)
    journal = Journal(directory)
    with pytest.raises(PaperError, match='missed next-open'):
        make_plan(snapshot, client.context(), journal)
    journal.close()
    monkeypatch.setattr('quantcore.paper.corporate.reconcile_corporate', lambda *a,**kw: {'status':'reconciled'})
    monkeypatch.setattr('quantcore.paper.manual.collect_references', lambda *a: reference())
    result = rebalance(root,client,None,snapshot,'user-request-1','explicit user re-entry')
    assert result['submitted'] and len(result['orders']) == 5
    assert all(o['client_order_id'].endswith('-m1') for o in result['orders'])
    assert result['signal_evidence']['AAPL']['signal_close'] != 112
    assert result['references']['AAPL']['reference_close'] == 112
    assert all(len(o['client_order_id']) <= 48 for o in result['orders'])
    posts = sum(m == 'POST' for m,_ in broker.calls)
    assert rebalance(root,client,None,snapshot,'user-request-1','same request')['duplicate_request']
    assert sum(m == 'POST' for m,_ in broker.calls) == posts
    journal = Journal(directory)
    assert journal.db.execute('SELECT count(*) FROM decision_runs').fetchone()[0] == 2
    journal.close()


@pytest.mark.parametrize('change', ['future_collection','stale_bar','future_bar','missing_symbol','closed'])
def test_manual_reference_fails_closed(tmp_path, change):
    journal = Journal(tmp_path)
    data = reference()
    if change == 'future_collection':
        data['collected_at'] = '2026-11-25T15:01:00Z'
    if change == 'stale_bar':
        data['references']['AAPL']['bar_end'] = '2026-11-25T14:50:00Z'
    if change == 'future_bar':
        data['references']['AAPL']['bar_end'] = '2026-11-25T15:00:00Z'
    if change == 'missing_symbol':
        del data['references']['AAPL']
    journal.db.execute('CREATE TABLE manual_rebalances (revision INTEGER, request_id TEXT, state TEXT, data TEXT)')
    journal.db.execute('INSERT INTO manual_rebalances VALUES (1,?,?,?)', ('request','prepared',json.dumps(data)))
    with pytest.raises(PaperError):
        authorized_reference(journal,'request',pd.Timestamp('2026-11-25T15:00:00Z'),change != 'closed')
    with pytest.raises(PaperError, match='durable'):
        authorized_reference(journal,'unknown',pd.Timestamp('2026-11-25T15:00:00Z'),True)
    journal.close()


def test_minute_collection_excludes_incomplete_bar():
    class Data:
        def pages(self,*args):
            yield {'bars':{s:[{'t':'2026-11-25T14:57:00Z','o':111,'h':113,'l':110,'c':112,'v':100},
                {'t':'2026-11-25T14:59:00Z','o':111,'h':114,'l':110,'c':113,'v':100}] for s in SYMBOLS}}
    result = collect_references(Data(),{'timestamp':'2026-11-25T15:00:00Z','is_open':True})
    assert all(r['price'] == '112' for r in result['references'].values())


@pytest.fixture
def manual_closure(tmp_path):
    journal = Journal(tmp_path/'artifacts/paper_trading')
    journal.configure('account','momentum',100000)
    buyid, sellid = str(uuid4()), str(uuid4())
    buy = {'client_order_id':'qcp1-test-buy','symbol':'AAPL','side':'buy','qty':'10'}
    journal.save(buy,'filled',{'id':buyid,'filled_qty':'10'})
    activities = [{'id':'buy-fill','activity_type':'FILL','order_id':buyid,'symbol':'AAPL', 'side':'buy',
        'qty':'10','price':'100','transaction_time':'2026-11-25T14:31:00Z'},
        {'id':'sell-fill','activity_type':'FILL','order_id':sellid,'symbol':'AAPL','side':'sell',
        'qty':'10','price':'99','transaction_time':'2026-11-25T14:38:00Z'}]
    journal.db.execute('CREATE TABLE performance_activities (id TEXT PRIMARY KEY,data TEXT)')
    journal.db.execute('INSERT INTO performance_activities VALUES (?,?)', ('buy-fill',json.dumps(activities[0])))
    journal.db.commit()
    class Client:
        remote = {'id':sellid,'client_order_id':'manual-sell','symbol':'AAPL','side':'sell','qty':'10',
            'filled_qty':'10','filled_avg_price':'99','asset_class':'us_equity','status':'filled','type':'market'}
        def context(self):
            return {'account':{'id':'account'},'clock':{'timestamp':'2026-11-25T15:00:00Z'},'positions':[],'open_orders':[]}
        def activities(self,*a):
            return [activities[1]]
        def request(self, method,path):
            assert method == 'GET' and path == '/v2/orders/'+sellid
            return self.remote
    yield journal,Client(),activities
    journal.close()


def test_approved_manual_closure_preserves_own_orders_and_actual_loss(manual_closure):
    journal,client,activities = manual_closure
    with pytest.raises(PaperError, match='position differs'):
        own_inventory(client.context(),journal)
    result = adopt_closures(journal,client,{'AAPL':10},'2026-11-25T14:37:00Z','2026-11-25T14:39:00Z','user confirmed sell')
    assert result['realized_gross'] == '-10'
    assert len(journal.records()) == 1 and len(journal.external_records()) == 1
    assert own_inventory(client.context(),journal)['AAPL'] == Decimal(0)
    ledger = own_fill_ledger(journal.accounting_records(),activities,[])
    assert ledger['status'] == 'reconciled' and ledger['realized_gross'] == -10
    assert adopt_closures(journal,client,{'AAPL':10},'2026-11-25T14:37:00Z','2026-11-25T14:39:00Z','repeat')['status'] == 'already_recorded'


@pytest.mark.parametrize('bad', ['wrong_quantity','buy','unfilled','wrong_fill'])
def test_manual_approval_cannot_adopt_unapproved_trades(manual_closure,bad):
    journal,client,activities = manual_closure
    quantity = 11 if bad == 'wrong_quantity' else 10
    if bad == 'buy':
        client.remote = {**client.remote,'side':'buy'}
    if bad == 'unfilled':
        client.remote = {**client.remote,'status':'partially_filled'}
    if bad == 'wrong_fill':
        activities[1]['qty'] = '9'
    with pytest.raises(PaperError):
        adopt_closures(journal,client,{'AAPL':quantity},'2026-11-25T14:37:00Z','2026-11-25T14:39:00Z','confirmed')
    assert journal.external_records() == []
