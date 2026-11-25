"""Real news metadata and deterministic evidence extraction; no LLM sentiment claim."""

import hashlib
import html
import re

import pandas as pd

TOPICS = {
    "earnings": r"\b(earnings|eps|revenue|quarterly results)\b",
    "guidance": r"\b(guidance|outlook|forecast)\b",
    "risk": r"\b(risk|lawsuit|recall|investigation)\b",
    "capital": r"\b(dividend|buyback|repurchase|capital expenditure)\b",
}


def normalize_article(row, collected_at, analyzed_at):
    created, updated = pd.Timestamp(row["created_at"]), pd.Timestamp(row["updated_at"])
    if created.tzinfo is None or updated.tzinfo is None:
        raise ValueError("news timestamps require timezone")
    content = row.get("content") or ""
    text = html.unescape(
        re.sub("<[^>]+>", " ", row["headline"] + " " + (row.get("summary") or "") + " " + content)
    )
    text = re.sub(r"\s+", " ", text).strip()
    topics = [name for name, pattern in TOPICS.items() if re.search(pattern, text, flags=re.I)]
    # Evidence is a literal matched numeric expression, never an invented narrative/price probability.
    numbers = list(
        dict.fromkeys(
            re.findall(
                r"\$\s?\d[\d,.]*(?:\s?(?:billion|million|trillion))?|\b\d+(?:\.\d+)?%", text, flags=re.I
            )
        )
    )[:12]
    return {
        "id": str(row["id"]),
        "headline": row["headline"],
        "url": row["url"],
        "source": row.get("source"),
        "symbols": row.get("symbols") or [],
        "created_at": created.isoformat(),
        "updated_at": updated.isoformat(),
        "collected_at": collected_at,
        "analyzed_at": analyzed_at,
        "available_at": max(
            created, updated, pd.Timestamp(collected_at), pd.Timestamp(analyzed_at)
        ).isoformat(),
        "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
        "quality": "content_present" if content.strip() else "metadata_only",
        "analysis_method": "deterministic keyword/numeric extraction; not LLM",
        "topics": topics,
        "numeric_mentions": numbers,
        "sentiment": None,
        "llm_status": "unavailable",
    }
