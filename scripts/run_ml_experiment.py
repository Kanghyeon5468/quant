"""Save a reproducible, read-only market ML experiment in the research artifact directory."""
import argparse
from pathlib import Path

from quantcore.core.files import atomic_json
from quantcore.data.storage.market import MarketRepository
from quantcore.machine_learning.research import extended_validation

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbol")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    market = MarketRepository(root/"datasets").load()
    result = extended_validation(market.frames[args.symbol].signal_close)
    if result["status"] != "ok":
        raise SystemExit(result["reason"])
    path = root/"artifacts/research/experiments"/f'{args.symbol}-{result["experiment"]}.json'
    atomic_json(path, {"symbol": args.symbol, "dataset_version": market.version, **result})
    print(path.relative_to(root))
