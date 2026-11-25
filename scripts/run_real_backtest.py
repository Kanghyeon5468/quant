import argparse
import json
from pathlib import Path

from quantcore.research.real_equities import export_actual, latest_snapshot

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    report = export_actual(root, args.snapshot or latest_snapshot(root))
    for row in report['results']:
        print(row['symbol'], row['strategy'], f"net {row['total_return']:.4%}",
              f"gross {row['gross_total_return']:.4%}", f"MDD {row['max_drawdown']:.4%}")
    print(json.dumps(report['metadata'], indent=2))
