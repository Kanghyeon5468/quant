"""Explicit paper-only plan/run/status/cancel commands; never starts a daemon."""
import argparse
import json
from decimal import Decimal
from pathlib import Path

from quantcore.paper.client import PaperClient, PaperError
from quantcore.paper.runner import cancel_own, run_once, status
from quantcore.research.real_equities import latest_snapshot

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['plan', 'run', 'status', 'cancel'])
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--strategy', choices=['momentum', 'mean_reversion'], default='momentum')
    parser.add_argument('--budget', type=Decimal, help='Use the journal budget by default; ceiling 100000. Changes require set_paper_budget.py.')
    parser.add_argument('--snapshot', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    directory = root/'artifacts/paper_trading'
    client = PaperClient(args.env_file)
    try:
        if args.command in ('plan', 'run'):
            result = run_once(client, directory, args.snapshot or latest_snapshot(root),
                              args.strategy, args.budget, submit=args.command == 'run')
            print(json.dumps({k: result[k] for k in ['mode', 'strategy', 'budget_usd',
                'signal_session', 'execution_session', 'next_open', 'submitted',
                'max_new_buy_limit_notional_usd', 'decisions']}, indent=2))
        elif args.command == 'status':
            result = status(client, directory)
            print(json.dumps({'mode': result['mode'], 'checked_at': result['checked_at'], 'clock': result['clock'],
                'orders': [{'symbol': r['payload']['symbol'], 'side': r['payload']['side'],
                    'qty': r['payload']['qty'], 'status': r['state'],
                    'filled_qty': (r['response'] or {}).get('filled_qty', '0'),
                    'filled_avg_price': (r['response'] or {}).get('filled_avg_price')}
                    for r in result['journal']]}, indent=2))
        else:
            print(json.dumps({'mode': 'paper', 'orders': [{'symbol': r['payload']['symbol'], 'status': r['state']}
                for r in cancel_own(client, directory)]}, indent=2))
    except PaperError as error:
        parser.exit(1, f'Paper trading stopped: {error}\n')
    finally:
        client.close()
