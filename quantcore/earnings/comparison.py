"""Descriptive quarter comparisons grounded in actual text counts; no invented outlook revision."""

import re

TOPICS = {
    "demand": r"\bdemand\b",
    "guidance": r"\b(guidance|outlook|forecast)\b",
    "risk": r"\b(risk|uncertainty|headwind)\b",
    "capex": r"\b(capex|capital expenditure)\b",
    "competition": r"\b(competition|competitive|competitor)\b",
}


def compare(documents):
    result = []
    quarter = {"First Quarter": 1, "Second Quarter": 2, "Third Quarter": 3, "Fourth Quarter": 4}
    for symbol in sorted({d["symbol"] for d in documents}):
        rows = sorted(
            [d for d in documents if d["symbol"] == symbol and d["kind"] == "earnings_release"],
            key=lambda d: (d["fiscal_year"], quarter.get(d["quarter"], 0)),
        )
        if len(rows) < 2:
            continue
        old, current = rows[-2:]

        def counts(d):
            text = "\n".join(s["text"] for s in d["segments"])
            words = max(1, len(text.split()))
            return {
                k: {
                    "mentions": len(re.findall(v, text, re.I)),
                    "mentions_per_1000_words": len(re.findall(v, text, re.I)) * 1000 / words,
                }
                for k, v in TOPICS.items()
            }

        before, after = counts(old), counts(current)
        result.append(
            {
                "symbol": symbol,
                "prior_quarter": old["quarter"],
                "current_quarter": current["quarter"],
                "prior_fiscal_year": old["fiscal_year"],
                "current_fiscal_year": current["fiscal_year"],
                "prior_url": old["source_url"],
                "current_url": current["source_url"],
                "available_at": max(old["available_at"], current["available_at"]),
                "topics": [
                    {
                        "topic": k,
                        "prior": before[k],
                        "current": after[k],
                        "mention_change": after[k]["mentions"] - before[k]["mentions"],
                    }
                    for k in TOPICS
                ],
                "method": "literal term frequency; mentions are not sentiment, guidance revisions or earnings surprise",
            }
        )
    return result
