"""Explicit local paper maintenance/re-entry. Never called by the automatic scheduler or web API."""

import argparse
import json
from pathlib import Path

from quantcore.data.providers.alpaca import AlpacaData
from quantcore.information.store import now
from quantcore.paper.client import PaperClient, PaperError
from quantcore.paper.corporate import reconcile_corporate
from quantcore.paper.journal import Journal
from quantcore.paper.manual import adopt_closures, rebalance
from quantcore.paper.market import atomic_json
from quantcore.paper.performance import collect_performance


def approve(root, client, args):
    directory = root/'artifacts/paper_trading'
    mutex, journal = Journal(directory/'automation'), Journal(directory)
    try:
        with mutex.lock():
            with journal.lock():
                result = adopt_closures(journal,client,dict(item.split('=') for item in args.quantities),
                    args.after,args.until,args.reason)
            corporate = reconcile_corporate(client,root,refresh=False)
            performance = collect_performance(client,root)
            if corporate['status'] != 'reconciled' or performance['pnl']['ledger_status'] != 'reconciled':
                raise PaperError('reconciliation is incomplete; existing automation block preserved')
            path = directory/'automation/state.json'
            state = json.loads(path.read_text()) if path.exists() else {}
            if args.acknowledge_reconciled_block and state.get('blocked'):
                if not state.get('error',{}).get('message','').startswith('corporate action requires review:'):
                    raise PaperError('unrelated automation block requires separate review')
                atomic_json(directory/'manual_audit/closure_block_resolution.json',{
                    'reviewed_at':now(),'reason':args.reason,'previous_state':state,'closure':result,
                    'corporate_status':corporate['status'],'ledger_status':performance['pnl']['ledger_status']})
                state.update(blocked=False,consecutive_failures=0,phase='reviewed',manual_reviewed_at=now())
                state.pop('error',None)
                state.pop('retry_after',None)
                atomic_json(path,state)
            return {**result,'ledger_status':performance['pnl']['ledger_status'],
                'cash':performance['account']['cash'],'realized_gross':performance['pnl']['realized_gross'],
                'automation_blocked':state.get('blocked',False),'stop_preserved':(directory/'STOP').exists()}
    finally:
        journal.close()
        mutex.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file',required=True)
    parser.add_argument('--reason',required=True)
    sub = parser.add_subparsers(dest='action',required=True)
    adoption = sub.add_parser('approve-closures')
    adoption.add_argument('--quantities',nargs='+',required=True,help='Explicit SYMBOL=whole-shares pairs')
    adoption.add_argument('--after',required=True)
    adoption.add_argument('--until',required=True)
    adoption.add_argument('--acknowledge-reconciled-block',action='store_true')
    trading = sub.add_parser('rebalance')
    trading.add_argument('--request-id',required=True,help='Stable ID: reuse it when checking a previous request')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    client = PaperClient(args.env_file)
    data_client = None
    try:
        if args.action == 'approve-closures':
            result = approve(root,client,args)
        else:
            pointer = root/'datasets/paper_equities/latest.json'
            if not pointer.exists():
                pointer = root/'datasets/real_equities/latest.json'
            snapshot = Path(json.loads(pointer.read_text())['snapshot_directory'])
            data_client = AlpacaData(args.env_file)
            raw = rebalance(root,client,data_client,snapshot,args.request_id,args.reason)
            result = {k:raw.get(k) for k in ('status','duplicate_request','manual_request_id','submitted',
                'signal_session','execution_session','max_new_buy_limit_notional_usd')}
            result['orders'] = [{k:v for k,v in row.items() if k != 'client_order_id'} for row in raw.get('orders',[])]
            result['risk_status'] = raw.get('risk',{}).get('status')
        print(json.dumps(result,ensure_ascii=False,indent=2))
    finally:
        client.close()
        if data_client:
            data_client.close()
