import argparse
from pathlib import Path

from quantcore.data.providers.alpaca import collect_snapshot

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--env-file', type=Path, help='Read-only path authorized by the user; values are never copied.')
    parser.add_argument('--start', default='2025-07-01')
    args = parser.parse_args()
    snapshot = collect_snapshot('datasets/real_equities', args.env_file, args.start)
    print('Completed actual-data snapshot:', snapshot)
