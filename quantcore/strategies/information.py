"""Auditable information overlay. Heuristic scores are never probabilities or fitted forecasts."""

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from quantcore.information.service import InformationService


class DecisionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    enabled: bool = False
    weights: dict[str, float] = Field(
        default_factory=lambda: {"financials": 0.45, "institutions": 0.2, "news": 0.25, "earnings": 0.1}
    )
    minimum_multiplier: float = Field(default=0.5, ge=0, le=1)
    neutral_multiplier: float = Field(default=0.75, ge=0, le=1)
    news_hours: int = Field(default=48, ge=1, le=168)
    max_statement_days: int = Field(default=200, ge=30, le=400)
    max_institution_days: int = Field(default=150, ge=45, le=365)

    @property
    def version(self):
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()[:12]


def policy_at(root):
    path = Path(root) / "configs/decision_policy.json"
    policy = DecisionPolicy.model_validate_json(path.read_text()) if path.exists() else DecisionPolicy()
    if (
        set(policy.weights) != {"financials", "institutions", "news", "earnings"}
        or any(not np.isfinite(v) or v < 0 for v in policy.weights.values())
        or sum(policy.weights.values()) <= 0
    ):
        raise ValueError("invalid information weights")
    if policy.minimum_multiplier > policy.neutral_multiplier:
        raise ValueError("invalid multiplier interval")
    return policy


def clip(value):
    return float(np.clip(value, -1, 1))


def evaluate(service, symbol, cutoff, policy):
    cutoff = pd.Timestamp(cutoff)
    if cutoff.tzinfo is None:
        raise ValueError("decision cutoff requires timezone")
    financial = service.financials(symbol, cutoff)
    information = service.report(symbol, cutoff)
    values = {"financials": None, "institutions": None, "news": None, "earnings": None}
    sources = {}
    details = {}
    end = financial.get("period_end")
    if end and 0 <= (cutoff.date() - pd.Timestamp(end).date()).days <= policy.max_statement_days:
        metrics = {m["name"]: m["value"] for m in financial["metrics"]}
        raw = [metrics.get("revenue_growth"), metrics.get("roe"), metrics.get("operating_margin")]
        measured = [clip(v / scale) for v, scale in zip(raw, [0.2, 0.25, 0.25]) if v is not None]
        if len(measured) >= 2:
            values["financials"] = float(np.mean(measured))
        sources["financials"] = {
            "url": financial.get("source_url"),
            "available_at": financial["available_at"],
            "period_end": end,
            "metrics": {k: metrics.get(k) for k in ("revenue_growth", "roe", "operating_margin")},
        }
    changes = []
    institutions = []
    for manager in information["institutions"]["managers"]:
        age = (cutoff.date() - pd.Timestamp(manager["report_date"]).date()).days
        previous = manager.get("prior_report_date")
        if (
            not previous
            or not 0 <= age <= policy.max_institution_days
            or not 60 <= (pd.Timestamp(manager["report_date"]) - pd.Timestamp(previous)).days <= 110
        ):
            continue
        rows = [r for r in manager["holdings"] if r["share_type"] == "SH" and not r.get("put_call")]
        if not rows:
            continue
        prior = sum(
            float(r["split_adjusted_prior_shares"])
            for r in rows
            if r.get("split_adjusted_prior_shares") is not None
        )
        current = sum(float(r["shares"]) for r in rows)
        if prior > 0:
            changes.append(clip((current / prior - 1) / 0.2))
        elif current > 0:
            changes.append(1.0)
        institutions.append(
            {
                "manager": manager["manager"],
                "report_date": manager["report_date"],
                "source_url": manager["source_url"],
                "available_at": manager["available_at"],
            }
        )
    if changes:
        values["institutions"] = float(np.mean(changes))
        sources["institutions"] = institutions
    articles = [
        a
        for a in information["news"]["articles"]
        if pd.Timedelta(0) <= cutoff - pd.Timestamp(a["created_at"]) <= pd.Timedelta(hours=policy.news_hours)
    ]
    if articles:
        risk = sum("risk" in a["topics"] for a in articles)
        score = -min(risk / 3, 1)
        values["news"] = score
        sources["news"] = [
            {
                "id": a["id"],
                "updated_at": a["updated_at"],
                "url": a["url"],
                "available_at": a["available_at"],
                "topics": a["topics"],
            }
            for a in articles
        ]
        details["news_method"] = "literal risk-topic count; not LLM sentiment"
    analyses = information.get("llm", {}).get("analyses", [])
    article_versions = {(a["id"], a["updated_at"]) for a in articles}
    scores = [
        a["sentiment"]
        for a in analyses
        if a.get("kind") == "news"
        and a.get("sentiment") is not None
        and (a.get("article_id"), a.get("article_updated_at")) in article_versions
    ]
    if scores:
        values["news"] = clip(0.7 * float(np.mean(scores)) + 0.3 * (values["news"] or 0))
        details["news_method"] = "validated LLM sentiment 70% + actual risk-topic evidence 30%"
    earnings = [
        a
        for a in analyses
        if a.get("kind") in ("transcript", "earnings_release", "cfo_commentary")
        and a.get("sentiment") is not None
        and pd.Timedelta(0) <= cutoff - pd.Timestamp(a["available_at"]) <= pd.Timedelta(days=120)
    ]
    if earnings:
        # A partial chunk must not stand in for an entire current-quarter document.
        quarter_order = {"First Quarter": 1, "Second Quarter": 2, "Third Quarter": 3, "Fourth Quarter": 4}
        latest_quarter = max(
            (
                (d.get("fiscal_year", 0), quarter_order.get(d.get("quarter"), 0))
                for d in information.get("earnings_calls", {}).get("documents", [])
            ),
            default=None,
        )
        grouped = {}
        for row in earnings:
            quarter = (row.get("fiscal_year", 0), quarter_order.get(row.get("quarter"), 0))
            if latest_quarter and quarter != latest_quarter:
                continue
            grouped.setdefault((row.get("document_key"), row["source_sha256"], row["model"]), []).append(row)
        complete = []
        for group in grouped.values():
            total = group[0].get("total_chunks", 1)
            if {r.get("chunk", 0) for r in group} == set(range(total)):
                complete.append(group)
        if complete:
            group = max(
                complete,
                key=lambda g: (
                    {"transcript": 3, "cfo_commentary": 2, "earnings_release": 1}.get(g[0]["kind"], 0),
                    max(r["available_at"] for r in g),
                ),
            )
            values["earnings"] = float(np.mean([r["sentiment"] for r in group]))
            sources["earnings"] = {
                k: group[0].get(k) for k in ("source_url", "source_sha256", "model", "kind")
            }
            sources["earnings"]["available_at"] = max(r["available_at"] for r in group)
    eligible = {k: v for k, v in values.items() if v is not None and policy.weights[k] > 0}
    score = (
        sum(v * policy.weights[k] for k, v in eligible.items()) / sum(policy.weights[k] for k in eligible)
        if eligible
        else None
    )
    multiplier = (
        float(
            np.clip(
                policy.neutral_multiplier + (1 - policy.neutral_multiplier) * score,
                policy.minimum_multiplier,
                1,
            )
        )
        if score is not None
        else 1.0
    )
    return {
        "status": "applied" if eligible else "unavailable",
        "symbol": symbol,
        "cutoff": cutoff.isoformat(),
        "policy_version": policy.version,
        "scores": values,
        "combined_score": score,
        "multiplier": multiplier,
        "missing_components": [k for k, v in values.items() if v is None],
        "sources": sources,
        "details": details,
        "interpretation": "predefined allocation heuristic, not a learned forecast or price-up probability",
        "no_data_behavior": "retain base price strategy with explicit missing evidence",
    }


def decision_context(root, symbols, cutoff, data_directory=None):
    policy = policy_at(root)
    if not policy.enabled:
        return None
    service = InformationService(data_directory or Path(root) / "datasets")
    rows = {}
    for symbol in symbols:
        try:
            rows[symbol] = evaluate(service, symbol, cutoff, policy)
        except (ValueError, KeyError, OSError, TypeError) as error:
            rows[symbol] = {
                "status": "blocked",
                "symbol": symbol,
                "multiplier": 1.0,
                "reason": str(error)[:180],
                "cutoff": str(cutoff),
                "policy_version": policy.version,
                "scores": {},
                "sources": {},
            }
    return {
        "policy_version": policy.version,
        "cutoff": str(cutoff),
        "rows": rows,
        "policy": policy.model_dump(),
    }
