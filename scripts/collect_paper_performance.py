"""Refresh account performance using GET requests only; never submits/cancels an order."""
import argparse
import json
from pathlib import Path

from quantcore.paper.client import PaperClient
from quantcore.paper.performance import collect_performance

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path)
    args = parser.parse_args()
    client = PaperClient(args.env_file)
    try:
        report = collect_performance(client, Path(__file__).resolve().parents[1])
        print(json.dumps({k: report[k] for k in ('checked_at', 'status', 'account', 'pnl', 'execution', 'sections')}, indent=2))
    finally:
        client.close()
