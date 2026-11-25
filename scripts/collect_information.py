"""Refresh actual SEC financials/13F and Alpaca news; no generated data fallback."""

import argparse
import json
from pathlib import Path

from quantcore.information.collector import refresh

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--reuse-probe", action="store_true", help="reuse verified actual initial CompanyFacts downloads"
    )
    args = parser.parse_args()
    result = refresh(Path(__file__).resolve().parents[1], args.env_file, args.force, args.reuse_probe)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(1 if any(r["status"] == "failed" for r in result.values()) else 0)
