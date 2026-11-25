"""Run the frozen chronological research plan on authorized local minute data; no broker calls."""
from pathlib import Path

from quantcore.research.walk_forward import run_validation

if __name__ == '__main__':
    run_validation(Path(__file__).resolve().parents[1])
