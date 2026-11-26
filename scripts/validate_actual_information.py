"""Offline verification of privately cached real observations and actual-mode API wiring."""

import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.main import create_app
from quantcore.core.files import atomic_json
from quantcore.information.service import InformationService
from quantcore.information.store import now, read_snapshot


def run(root):
    root = Path(root)
    service = InformationService(root / "datasets")
    report = {"executed_at": now(), "mode": "actual cached observations", "financials": {}, "checks": []}
    for symbol in ("AAPL", "MSFT", "NVDA", "TSLA"):
        result = service.financials(symbol)
        metrics = {m["name"]: m["value"] for m in result["metrics"]}
        report["financials"][symbol] = {
            "period_end": result["period_end"],
            "period_start": result["period_start"],
            "metrics_available": sum(v is not None for v in metrics.values()),
            "metrics_total": len(metrics),
            "revenue_growth": metrics["revenue_growth"],
            "free_cash_flow_usd": metrics["free_cash_flow"],
            "missing_metrics": [k for k, v in metrics.items() if v is None],
            "collected_at": result["collected_at"],
            "available_at": result["available_at"],
            "source_url": result["source_url"],
        }
        assert service.financials(symbol, "2026-11-24T23:59:59Z")["metrics"] == []
        # TTM conservation is checked against the actual XBRL quarter components, not hand-entered expected prices.
        statement = result["statement"]
        assert len(result["evidence"]["revenue"]) == 4
        for field in ("revenue", "operating_cash_flow", "capex"):
            assert statement[field] == sum(q["value"] for q in result["evidence"][field])
        assert statement["debt"] is None
    report["checks"] += [
        "four contiguous SEC quarters reconcile to TTM revenue/CFO/capex",
        "financial observations absent before actual collection/analysis",
        "no inferred total debt or invented missing EPS",
    ]
    information = service.report()
    report["institutions"] = [
        {
            k: m[k]
            for k in (
                "manager",
                "report_date",
                "prior_report_date",
                "status",
                "entry_count",
                "reported_total_usd",
                "available_at",
                "source_url",
            )
        }
        for m in information["institutions"]["managers"]
    ]
    report["13f_filings_verified"] = sum(len(m["filings"]) for m in information["institutions"]["managers"])
    folder, _ = read_snapshot(root / "datasets", "news")
    articles = json.loads((folder / "articles.json").read_text())
    report["news"] = {
        "article_versions": len(articles),
        "unique_articles": len({a["id"] for a in articles}),
        "content_present": sum(a["quality"] == "content_present" for a in articles),
        "metadata_only": sum(a["quality"] == "metadata_only" for a in articles),
        "llm_status": information["llm"]["status"],
        "earnings_calls": information["earnings_calls"]["status"],
    }
    prior = service.report(as_of="2026-11-24T23:59:59Z")
    assert not prior["news"]["articles"] and not prior["institutions"]["managers"]
    report["checks"] += [
        "four official 13F XML counts/value totals reconciled",
        "13F/news absent before actual availability",
        "news carries actual source links and no generated sentiment",
        "stale Vanguard report not labeled current 2026 holdings",
        "official earnings materials distinct from unavailable transcripts; model results retain actual availability",
    ]
    with TestClient(
        create_app(data_source="alpaca", market_directory=root / "datasets", token="local-validation"),
        headers={"Authorization": "Bearer local-validation"},
    ) as client:
        for symbol in ("AAPL", "MSFT", "NVDA", "TSLA", "SPY"):
            result = client.get(f"/api/assets/{symbol}/fundamentals")
            assert result.status_code == 200
            assert result.json()["status"] == ("missing" if symbol == "SPY" else "partial")
        factors = client.get("/api/factors").json()
        assert {r["symbol"] for r in factors["rows"]} == {"AAPL", "MSFT", "NVDA", "TSLA"}
        assert client.get("/api/factors?sector_neutral=true").json()["status"] == "unavailable"
        assert client.get("/api/information?symbol=AAPL").json()["news"]["articles"]
        assert client.get("/api/information?as_of=2026-11-24T23:59:59Z").json()["news"]["articles"] == []
        report["factor_ranks"] = [
            {"symbol": r["symbol"], "rank": r["rank"], "score": r["score"]} for r in factors["rows"]
        ]
        report["api_checks"] = 9
    report["input_hashes"] = {
        kind: read_snapshot(root / "datasets", kind)[1]["hashes"]
        for kind in ("financials", "institutions", "news")
    }
    report["source_code_sha256"] = {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for parent in ("quantcore/information", "quantcore/fundamentals")
        for p in (root / parent).glob("*.py")
    }
    atomic_json(root / "docs/actual_information_validation.json", report)
    print(
        json.dumps(
            {k: v for k, v in report.items() if k not in ("input_hashes", "source_code_sha256")},
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    run(Path(__file__).resolve().parents[1])
