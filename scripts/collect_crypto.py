"""Refresh two historical Coinbase markets with public GETs."""
from pathlib import Path

from quantcore.data.providers.coinbase_public import collect

if __name__ == "__main__":
    print(collect(Path(__file__).resolve().parents[1] / "datasets"))
