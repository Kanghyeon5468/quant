"""Import licensed USD/KRW research OHLCV without touching the portfolio universe."""
import argparse
import json
from pathlib import Path

from quantcore.data.providers.research_files import import_csv

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metadata", type=Path)
    parser.add_argument("csv", type=Path)
    args = parser.parse_args()
    path, manifest = import_csv(Path(__file__).resolve().parents[1]/"datasets", json.loads(args.metadata.read_text()), args.csv)
    print({"snapshot": path.name, "bars": manifest["bars"]})
