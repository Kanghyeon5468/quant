"""Actual NVDA 2024 split replay using authorized IEX minute bars; private raw cache."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import pandas as pd

from quantcore.backtesting.portfolio import load_minutes, replay
from quantcore.core.files import atomic_json
from quantcore.data.calendar import sessions
from quantcore.data.providers.alpaca import AlpacaData, corporate_actions, regular_daily
from quantcore.information.store import now


def run(root, env_file):
    root = Path(root)
    directory = root / "datasets/split_validation/NVDA_2024"
    directory.mkdir(parents=True, exist_ok=True)
    if not (directory / "manifest.json").exists():
        client = AlpacaData(env_file)
        frames, pages, payload = [], [], {}
        try:
            for i, page in enumerate(
                client.pages(
                    "/v2/stocks/bars",
                    {
                        "symbols": "NVDA",
                        "start": "2024-02-01T00:00:00Z",
                        "end": "2024-06-15T00:00:00Z",
                        "timeframe": "1Min",
                        "adjustment": "raw",
                        "feed": "iex",
                        "limit": 10000,
                        "sort": "asc",
                    },
                )
            ):
                raw = json.dumps(page, sort_keys=True).encode()
                name = f"raw_bars_{i:03d}.json.gz"
                (directory / name).write_bytes(gzip.compress(raw))
                pages.append({"name": name, "sha256_uncompressed": hashlib.sha256(raw).hexdigest()})
                for symbol, rows in page["bars"].items():
                    if rows:
                        frames.append(pd.DataFrame(rows).assign(symbol=symbol))
            for page in client.pages(
                "/v1/corporate-actions",
                {"symbols": "NVDA", "start": "2024-02-01", "end": "2024-06-15", "limit": 1000},
            ):
                for kind, rows in page.get("corporate_actions", {}).items():
                    payload.setdefault(kind, []).extend(rows)
        finally:
            client.close()
        schedule = sessions("2024-02-01", "2024-06-14")
        actions = corporate_actions(payload, "2024-02-01", "2024-06-14")
        daily, n = regular_daily(pd.concat(frames, ignore_index=True), schedule, actions, symbols=("NVDA",))
        daily.to_parquet(directory / "prices.parquet", index=False)
        schedule.to_csv(directory / "calendar.csv")
        atomic_json(directory / "actions.json", payload)
        atomic_json(
            directory / "manifest.json",
            {
                "status": "complete",
                "data_mode": "historical",
                "source": "alpaca-iex-regular-1min",
                "feed": "iex",
                "symbols": ["NVDA"],
                "start": "2024-02-01",
                "end": "2024-06-14",
                "collected_at": now(),
                "hashes": {
                    f: hashlib.sha256((directory / f).read_bytes()).hexdigest()
                    for f in ["prices.parquet", "calendar.csv", "actions.json"]
                },
                "raw_pages": pages,
                "regular_minute_rows": n,
            },
        )
    daily, minutes, manifest = load_minutes(directory)
    # Existing strategy, single-slot mechanical accounting check; not the five-stock paper configuration.
    result = replay(daily, minutes, strategy="buy_hold", evaluation_sessions=10, risk_enabled=False)
    events = result["corporate_actions"]
    assert len(events) == 1 and events[0]["session"] == "2024-06-10" and float(events[0]["ratio"]) == 10
    assert events[0]["quantity_delta"] > 0 and result["audit"]["cash_inventory_nav_reconciled"]
    private = root / "artifacts/actual_split_validation.json"
    atomic_json(private, result)
    public = {
        "executed_at": now(),
        "source": "Alpaca IEX actual raw minute bars",
        "period": [result["curve"][0]["session"], result["curve"][-1]["session"]],
        "warmup_sessions": len(daily) - 10,
        "minute_rows": len(minutes),
        "raw_pages": len(manifest["raw_pages"]),
        "snapshot_hashes": manifest["hashes"],
        "corporate_actions": events,
        "metrics": result["metrics"],
        "audit": result["audit"],
        "scope": "NVDA single-slot buy_hold mechanical split verification; no risk filter; no paper strategy change",
        "limitations": [
            "IEX regular sessions only",
            "fractional settlement and ticker migration have no verified actual cases and remain review-blocked",
        ],
        "curve": result["curve"],
    }
    atomic_json(root / "docs/actual_split_validation.json", public)
    print(json.dumps({k: v for k, v in public.items() if k != "curve"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args()
    run(Path(__file__).resolve().parents[1], args.env_file)
