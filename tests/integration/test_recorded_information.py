"""Replay real private responses offline. No fabricated financial/news rows or network calls."""

import json
import shutil
from pathlib import Path

import pytest

from quantcore.data.reference.securities import load_reference
from quantcore.information.collector import financials, institutions, news, refresh
from quantcore.information.store import read_snapshot


@pytest.fixture
def recorded(tmp_path):
    root = Path(__file__).resolve().parents[2]
    if not (root / "datasets/information/institutions/latest.json").exists():
        pytest.skip("private real-response archive is not redistributed")
    financial, _ = read_snapshot(root / "datasets", "financials")
    institutional, _ = read_snapshot(root / "datasets", "institutions")
    ref = load_reference(root)
    target = tmp_path / "datasets/reference" / Path(ref["directory"]).name
    shutil.copytree(ref["directory"], target)
    (target.parent / "latest.json").write_text(json.dumps({"snapshot_directory": target.name}))
    return root, tmp_path, financial, institutional


def test_real_recorded_companyfacts_and_13f_pipeline(recorded):
    _, root, financial, institutional = recorded

    class RecordedSEC:
        def get(self, url):
            if "/companyfacts/" in url or "/submissions/" in url:
                cik = int(url.split("CIK")[1].split(".")[0])
                symbols = {320193: "AAPL", 789019: "MSFT", 1045810: "NVDA", 1318605: "TSLA"}
                if cik in symbols:
                    name = (
                        ("companyfacts_" if "/companyfacts/" in url else "submissions_")
                        + symbols[cik]
                        + ".json"
                    )
                    return (financial / name).read_bytes()
                return (institutional / f"manager_{cik}.json").read_bytes()
            parts = url.split("/")
            accn = parts[-2]
            if parts[-1] == "index.json":
                return (institutional / f"{accn}_index.json").read_bytes()
            suffix = "cover" if parts[-1] == "primary_doc.xml" else "table"
            return (institutional / f"{accn}_{suffix}.xml").read_bytes()

    financial_result = financials(root, RecordedSEC())
    assert financial_result["AAPL"]["metrics_available"] == 13
    institutional_result = institutions(root, RecordedSEC())
    assert institutional_result["filings"] == 4 and institutional_result["failures"] == []
    _, manifest = read_snapshot(root / "datasets", "institutions")
    assert manifest["managers"] == 2


def test_real_recorded_news_dedup_and_failure_retains_inputs(recorded, monkeypatch):
    source, root, _, _ = recorded
    candidates = sorted((source / "datasets/information/news").glob("*/raw_news_000.json"))
    first = next(p.parent for p in candidates if json.loads(p.read_text()).get("news"))
    pages = [json.loads(p.read_text()) for p in sorted(first.glob("raw_news_*.json"))]

    class RecordedAlpaca:
        def __init__(self, env):
            pass

        def pages(self, path, params):
            assert path == "/v1beta1/news"
            yield from pages

        def close(self):
            pass

    monkeypatch.setattr("quantcore.information.collector.AlpacaData", RecordedAlpaca)
    one = news(root, None)
    first_folder, _ = read_snapshot(root / "datasets", "news")
    first_rows = json.loads((first_folder / "articles.json").read_text())
    two = news(root, None)
    second_folder, _ = read_snapshot(root / "datasets", "news")
    assert one["articles"] == two["articles"] == 69
    assert first_rows == json.loads((second_folder / "articles.json").read_text())
    latest = (root / "datasets/information/news/latest.json").read_bytes()

    def failed(*args, **kwargs):
        raise RuntimeError("recorded failure exercise")

    for name in ("financials", "institutions", "news"):
        monkeypatch.setattr("quantcore.information.collector." + name, failed)

    class UnusedSEC:
        def __init__(self, root):
            pass

        def close(self):
            pass

    monkeypatch.setattr("quantcore.information.collector.SECData", UnusedSEC)
    result = refresh(root, None, force=True)
    assert all(r["status"] == "failed" and r["failures"] == 1 for r in result.values())
    assert (root / "datasets/information/news/latest.json").read_bytes() == latest
    assert refresh(root, None) == result  # bounded retries: no immediate repeated requests
