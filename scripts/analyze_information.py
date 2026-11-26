"""Run only the explicitly configured language model on privately cached actual sources."""

import json
from pathlib import Path

from quantcore.analysis.worker import run

if __name__ == "__main__":
    print(json.dumps(run(Path(__file__).resolve().parents[1]), ensure_ascii=False, indent=2))
