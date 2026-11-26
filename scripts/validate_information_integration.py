"""Validate actual cached sources, allocation preview and the absence of unconfigured model output."""

import json
import sqlite3
from pathlib import Path

from quantcore.analysis.llm import readiness, settings
from quantcore.analysis.worker import news_documents
from quantcore.core.files import atomic_json
from quantcore.data.providers.alpaca import SYMBOLS, load_snapshot
from quantcore.information.service import InformationService
from quantcore.information.store import now, read_snapshot
from quantcore.strategies.information import decision_context
from quantcore.strategies.orders import slot_orders


def run(root):
    root = Path(root)
    cutoff = now()
    service = InformationService(root / "datasets")
    current = service.report(as_of=cutoff)
    model_readiness = readiness(settings(root))
    model_analyses = current["llm"]["analyses"]
    requests_file = root / "artifacts/llm/requests.sqlite3"
    request_count = 0
    if requests_file.exists():
        connection = sqlite3.connect(f"file:{requests_file.resolve()}?mode=ro", uri=True)
        try:
            request_count = connection.execute("SELECT count(*) FROM requests").fetchone()[0]
        finally:
            connection.close()
    folder, manifest = read_snapshot(root / "datasets", "earnings")
    documents = json.loads((folder / "documents.json").read_text())
    assert all(
        d["characters"] > 200 and d["public_at"] is None and not d["audio_downloaded"] for d in documents
    )
    assert not any(
        d["kind"] == "transcript" for d in documents
    )  # current official CDN robots access is blocked
    assert len(documents) == 6 and {d["symbol"] for d in documents} == {"AAPL", "NVDA"}
    context = decision_context(root, SYMBOLS, cutoff)
    before = decision_context(root, SYMBOLS, "2026-11-24T23:59:59Z")
    assert all(r["status"] == "unavailable" and r["multiplier"] == 1 for r in before["rows"].values())
    assert all(0.5 <= r["multiplier"] <= 1 for r in context["rows"].values())
    pointer = json.loads((root / "datasets/paper_equities/latest.json").read_text())
    daily, _, _ = load_snapshot(pointer["snapshot_directory"])
    histories = {s: daily[daily.symbol == s].sort_values("timestamp") for s in SYMBOLS}
    base = slot_orders(histories, dict.fromkeys(SYMBOLS, 0), 100000, 100000, "momentum")
    updated = slot_orders(
        histories,
        dict.fromkeys(SYMBOLS, 0),
        100000,
        100000,
        "momentum",
        target_multipliers={s: r["multiplier"] for s, r in context["rows"].items()},
    )
    assert sum(float(o["qty"]) * float(o["limit_price"]) for o in updated["orders"]) <= sum(
        float(o["qty"]) * float(o["limit_price"]) for o in base["orders"]
    )
    report = {
        "checked_at": cutoff,
        "source": "actual SEC + Alpaca + official issuer IR cached observations",
        "policy_version": context["policy_version"],
        "policy": context["policy"],
        "earnings": {
            "documents": len(documents),
            "coverage": manifest["coverage"],
            "failures": manifest["failures"],
            "document_types": {
                kind: sum(d["kind"] == kind for d in documents) for kind in {d["kind"] for d in documents}
            },
            "quarters": [
                {
                    k: d[k]
                    for k in (
                        "symbol",
                        "kind",
                        "fiscal_year",
                        "quarter",
                        "source_url",
                        "available_at",
                        "characters",
                    )
                }
                for d in documents
            ],
            "comparisons": len(json.loads((folder / "comparisons.json").read_text())),
        },
        "llm": {
            "readiness": model_readiness,
            "actual_analyses": len(model_analyses),
            "actual_requests": request_count,
            "models": sorted({r["model"] for r in model_analyses}),
            "real_news_documents_prepared": len(news_documents(root / "datasets")),
        },
        "allocation": {
            s: {
                k: r.get(k)
                for k in ("status", "scores", "combined_score", "multiplier", "missing_components")
            }
            for s, r in context["rows"].items()
        },
        "preview": {
            "assumption": "flat account, same $100000 cash and price strategy; broker risk applied during actual execution",
            "base_orders": base["orders"],
            "information_orders": updated["orders"],
        },
        "checks": [
            "real sources and manifest hashes verified",
            "no mock LLM/transcript data",
            "previous-day cutoff has no later-collected information",
            "only completed current-quarter evidence can supply earnings sentiment",
            "allocation never exceeds base price-strategy exposure",
            "official transcript access failure is visible",
        ],
        "limitations": [
            "allocation formula is a predefined heuristic, not a trained predictor or validated performance improvement",
            "no retrospective financial/news feature backfill; only current forward observations are eligible",
        ],
    }
    atomic_json(root / "docs/information_decision_validation.json", report)
    print(
        json.dumps(
            {k: v for k, v in report.items() if k not in ("policy", "earnings")}, ensure_ascii=False, indent=2
        )
    )


if __name__ == "__main__":
    run(Path(__file__).resolve().parents[1])
