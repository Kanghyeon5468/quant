"""Collect only official published earnings text; no models, audio or trading calls."""

import json
from pathlib import Path

from quantcore.earnings.collector import collect

if __name__ == "__main__":
    print(json.dumps(collect(Path(__file__).resolve().parents[1]), ensure_ascii=False, indent=2))
