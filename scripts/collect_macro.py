"""Refresh public research data without broker or LLM credentials."""
from pathlib import Path

from quantcore.macro.public import collect

if __name__ == "__main__":
    result = collect(Path(__file__).resolve().parents[1] / "datasets")
    print({"status": result["status"], "series": list(result["series"]), "failures": result["failures"]})
