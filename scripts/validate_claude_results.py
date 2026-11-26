"""Offline audit of actual Claude receipts and evidence; never sends another model request."""

import hashlib
import json
import sqlite3
from pathlib import Path

from quantcore.analysis.anthropic import ANTHROPIC_API_VERSION, DEFAULT_OPUS_MODEL
from quantcore.analysis.llm import readiness, settings, verify
from quantcore.analysis.worker import news_documents
from quantcore.core.files import atomic_json
from quantcore.information.service import InformationService
from quantcore.information.store import now, read_snapshot


def run(root):
    root = Path(root)
    ready = readiness(settings(root))
    assert (
        ready["status"] == "configured"
        and ready["provider"] == "anthropic"
        and ready["model"] == DEFAULT_OPUS_MODEL
    )
    folder, manifest = read_snapshot(root / "datasets", "analysis")
    analyses = [
        r
        for r in json.loads((folder / "analyses.json").read_text())
        if r["provider"] == "anthropic" and r["model"] == DEFAULT_OPUS_MODEL
    ]
    earnings = read_snapshot(root / "datasets", "earnings")
    docs = news_documents(root / "datasets") + json.loads((earnings[0] / "documents.json").read_text())
    by_source = {d["source_sha256"]: d for d in docs}
    for row in analyses:
        assert row.get("response_model") == DEFAULT_OPUS_MODEL
        document = by_source[row["source_sha256"]]
        assert verify({"claims": row["claims"]}, document["segments"])["claims"] == row["claims"]
    assert any(r["kind"] == "news" for r in analyses)
    assert any(r["kind"] == "earnings_release" for r in analyses)
    db = sqlite3.connect(f"file:{(root / 'artifacts/llm/requests.sqlite3').resolve()}?mode=ro", uri=True)
    try:
        counts = dict(db.execute("SELECT status,count(*) FROM requests GROUP BY status").fetchall())
    finally:
        db.close()
    usage = {
        k: sum((r.get("usage") or {}).get(k, 0) for r in analyses) for k in ("input_tokens", "output_tokens")
    }
    view = InformationService(root / "datasets").report()
    assert view["llm"]["status"] == "available" and len(view["llm"]["analyses"]) >= len(analyses)
    report = {
        "checked_at": now(),
        "provider": "anthropic",
        "model": DEFAULT_OPUS_MODEL,
        "api_version": ANTHROPIC_API_VERSION,
        "model_lookup": json.loads((root / "artifacts/claude/connection.json").read_text()),
        "actual_analyses": len(analyses),
        "by_kind": {kind: sum(r["kind"] == kind for r in analyses) for kind in {r["kind"] for r in analyses}},
        "verified_claims": sum(len(r["claims"]) for r in analyses),
        "request_status_counts": counts,
        "usage_tokens": usage,
        "snapshot_id": manifest["snapshot_id"],
        "evidence_reverified": True,
        "analyses": [
            {
                "kind": r["kind"],
                "symbols": r["symbols"],
                "source_url": r["source_url"],
                "source_sha256": r["source_sha256"],
                "model": r["model"],
                "response_model": r["response_model"],
                "claims": len(r["claims"]),
                "analyzed_at": r["analyzed_at"],
                "available_at": r["available_at"],
            }
            for r in analyses
        ],
        "limits": {"requests_per_refresh": 3, "requests_per_day": 20},
        "code_sha256": {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (root / "quantcore/analysis").glob("*.py")
        },
        "notes": [
            "token counts are provider-reported usage, not a billing statement",
            "model interpretations are not calibrated price probabilities or verified performance improvement",
            "existing paper session timing, order dedup and risk limits remain in force",
        ],
    }
    atomic_json(root / "docs/claude_opus_validation.json", report)
    print(
        json.dumps(
            {k: v for k, v in report.items() if k not in ("analyses", "code_sha256")},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    run(Path(__file__).resolve().parents[1])
