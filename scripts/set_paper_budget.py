"""Explicit paper budget change with own-order cancellation and revision-safe rebalancing."""
import argparse
import json
from decimal import Decimal
from pathlib import Path

from quantcore.paper.budget import change_budget
from quantcore.paper.client import PaperClient
from quantcore.paper.market import refresh_snapshot

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--budget', type=Decimal, required=True)
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--resume', action='store_true', help='Resume automatic execution after migration')
    parser.add_argument('--execute', action='store_true', help='Submit the new simulated target orders now')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    client = PaperClient(args.env_file)
    try:
        clock = client.request('GET', '/v2/clock')
        snapshot = refresh_snapshot(root, args.env_file, clock['timestamp'])
        result = change_budget(client, root/'artifacts/paper_trading', snapshot, args.budget,
                               execute=args.execute, resume_after=args.resume)
        print(json.dumps({k: result[k] for k in ('mode', 'old_budget_usd', 'budget_usd', 'budget_revision', 'submitted')}, indent=2))
        print(json.dumps([{'symbol': r['payload']['symbol'], 'side': r['payload']['side'],
                          'qty': r['payload']['qty'], 'status': r['state'],
                          'filled_qty': (r['response'] or {}).get('filled_qty')}
                         for r in result['journal']], indent=2))
    finally:
        client.close()
