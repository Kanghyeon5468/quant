"""Deterministic comparative briefs using cited model evidence already on disk."""


def comparative_brief(service, symbols):
    if not hasattr(service, "information"):
        return {"status": "unavailable", "reason": "requires actual SEC and news archives"}
    rows = []
    for symbol in symbols:
        fundamentals = service.fundamentals(symbol)
        metrics = {r["name"]: r["value"] for r in fundamentals["metrics"]}
        information = service.information_report(symbol)
        analyses = sorted(information["llm"]["analyses"], key=lambda row: row["available_at"], reverse=True)
        claims = [
            {"summary": claim["summary"], "quote": claim["quote"], "model": entry["model"],
             "url": entry["source_url"], "available_at": entry["available_at"]}
            for entry in analyses[:3] for claim in entry["claims"][:2]
        ]
        rows.append({
            "symbol": symbol, "period_end": fundamentals.get("period_end"),
            "financial_url": fundamentals.get("source_url"), "available_at": fundamentals.get("available_at"),
            "revenue_growth": metrics.get("revenue_growth"), "operating_margin": metrics.get("operating_margin"),
            "hypothesis": "다음 공시에서도 현재의 매출 성장과 영업이익률이 유지되는지 검증합니다.",
            "counter_hypothesis": "다음 공시의 매출 성장 또는 영업이익률이 이 비교 기준보다 낮을 수 있습니다.",
            "claims": claims,
        })
    return {"status": "ok", "rows": rows, "basis": "SEC 수치와 저장된 Claude 근거를 비교합니다. 검증 가설은 고정 템플릿입니다."}
