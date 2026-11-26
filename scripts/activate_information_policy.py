"""Activate a reviewed information allocation policy in the existing authorized paper account."""

import argparse
import json
from pathlib import Path

from quantcore.paper.client import PaperClient
from quantcore.paper.information_policy import activate

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    pointer = root / "datasets/paper_equities/latest.json"
    snapshot = Path(json.loads(pointer.read_text())["snapshot_directory"])
    client = PaperClient(args.env_file)
    try:
        result = activate(root, client, snapshot)
    finally:
        client.close()
    print(json.dumps({k: v for k, v in result.items() if k != "analysis"}, ensure_ascii=False, indent=2))
