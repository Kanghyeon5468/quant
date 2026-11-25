"""Read-only, version-aware information views; no external API requests or synthetic fallback."""

import json
from pathlib import Path
from threading import RLock

import numpy as np
import pandas as pd

from quantcore.fundamentals.sec_facts import analyze_real, aware, normalize
from quantcore.information.store import read_snapshot

FACTORS = ["value", "momentum", "quality", "growth", "low_volatility", "liquidity"]


class InformationService:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.cache = {}
        self.lock = RLock()

    def snapshot(self, kind):
        pointer = self.directory / "information" / kind / "latest.json"
        if not pointer.exists():
            return None
        with self.lock:
            version = pointer.read_bytes()
            old = self.cache.get(kind)
            if old and old[0] == version:
                return old[1]
            result = read_snapshot(self.directory, kind)
            self.cache[kind] = version, result
            return result

    def financials(self, symbol, as_of=None):
        cutoff = aware(as_of or pd.Timestamp.now(tz="UTC"))
        snapshot = self.snapshot("financials")
        if not snapshot or not (snapshot[0] / f"normalized_{symbol}.json").exists():
            return {
                "status": "missing",
                "metrics": [],
                "reason": "실제 SEC 재무자료 없음 (ETF 포함). 모의자료로 대체하지 않습니다.",
            }
        folder, manifest = snapshot
        data = json.loads((folder / f"normalized_{symbol}.json").read_text())
        if aware(data["analyzed_at"]) > cutoff:
            return {
                "status": "missing",
                "metrics": [],
                "reason": "요청 시각에는 이 재무 관측·분석 결과가 아직 없었습니다.",
            }
        if as_of is not None:
            raw = json.loads((folder / f"companyfacts_{symbol}.json").read_text())
            recent = json.loads((folder / f"submissions_{symbol}.json").read_text())["filings"]["recent"]
            data = {
                **data,
                **normalize(
                    raw,
                    data["collected_at"],
                    dict(zip(recent["accessionNumber"], recent["acceptanceDateTime"])),
                    cutoff,
                ),
            }
        report = analyze_real(data)
        latest = data["records"][-1] if data["records"] else {}
        shares = [r for r in data["point_shares"] if aware(r["available_at"]) <= cutoff]
        share = shares[-1] if shares else None
        return {
            **report,
            "symbol": symbol,
            "financial_source": "SEC CompanyFacts",
            "financial_snapshot": manifest["snapshot_id"],
            "collected_at": data["collected_at"],
            "analyzed_at": data["analyzed_at"],
            "financial_as_of": cutoff.isoformat(),
            "available_at": max(latest.get("available_at", data["collected_at"]), data["analyzed_at"]),
            "statement": {k: v for k, v in latest.items() if k != "evidence"},
            "point_shares": share,
            "ttm_periods": len(data["records"]),
            "source_url": latest.get("source_url"),
        }

    def report(self, symbol=None, as_of=None):
        cutoff = aware(as_of or pd.Timestamp.now(tz="UTC"))
        news = self.snapshot("news")
        institutions = self.snapshot("institutions")
        articles = []
        if news:
            versions = json.loads((news[0] / "articles.json").read_text())
            unique = {}
            for row in versions:
                if aware(row["available_at"]) <= cutoff and (not symbol or symbol in row["symbols"]):
                    old = unique.get(row["id"])
                    if old is None or row["updated_at"] > old["updated_at"]:
                        unique[row["id"]] = row
            articles = sorted(unique.values(), key=lambda a: a["created_at"], reverse=True)
        managers = []
        if institutions:
            report = json.loads((institutions[0] / "report.json").read_text())
            # A report assembled today is not retroactively visible at the previous quarter-end.
            managers = [m for m in report["managers"] if aware(m["available_at"]) <= cutoff]
            if symbol:
                managers = [
                    {**m, "holdings": [r for r in m["holdings"] if r["ticker"] == symbol]} for m in managers
                ]
        if not symbol:
            managers = [
                {
                    **m,
                    "holdings_count": len(m["holdings"]),
                    "holdings": m["holdings"][:30] + [r for r in m["holdings"][30:] if r.get("ticker")],
                }
                for m in managers
            ]
        worker = self.directory / "information/worker_status.json"
        worker_status = json.loads(worker.read_text()) if worker.exists() else {}
        return {
            "worker": worker_status,
            "status": (
                "degraded"
                if any(v.get("status") in ("failed", "partial") for v in worker_status.values())
                else "ok"
            )
            if news or institutions
            else "unavailable",
            "mode": "historical",
            "as_of": cutoff.isoformat(),
            "symbol": symbol,
            "news": {
                "status": "available" if news else "unavailable",
                "articles": articles[:100],
                "matching_articles": len(articles),
                "snapshot": news[1] if news else None,
                "stale": bool(news and cutoff - aware(news[1]["collected_at"]) > pd.Timedelta(hours=2)),
            },
            "institutions": {
                "status": "available" if managers else "unavailable",
                "managers": managers,
                "snapshot": institutions[1] if institutions else None,
            },
            "earnings_calls": {
                "status": "unavailable",
                "reason": "공식 녹취록·허용 음성 수집 연결 없음. 어닝콜 자료는 생성하지 않습니다.",
            },
            "llm": {
                "status": "unavailable",
                "reason": "설정된 분석 모델/API 키 없음. 뉴스는 규칙 기반 키워드·수치 추출만 제공합니다.",
            },
            "model_integration": {
                "status": "research_only",
                "reason": "수집을 시작한 현재 시점 이전의 관측 이력이 없어 기존 매매·백테스트 입력에 소급 반영하지 않습니다.",
            },
        }


def real_factors(view, information, weights=None, sector_neutral=False):
    weights = dict.fromkeys(FACTORS, 1.0) if weights is None else weights
    if (
        set(weights) - set(FACTORS)
        or any(not np.isfinite(v) or v < 0 for v in weights.values())
        or sum(weights.values()) <= 0
    ):
        raise ValueError("nonnegative finite known factor weights with positive sum required")
    if sector_neutral:
        return {
            "status": "unavailable",
            "rows": [],
            "reason": "실제 GICS 섹터 자료가 없습니다. 프로젝트 리스크 그룹을 GICS로 대체하지 않습니다.",
        }
    rows, unavailable = [], []
    cutoff = pd.Timestamp.now(tz="UTC")
    for symbol, frame in view.frames.items():
        financial = information.financials(symbol)
        statement = financial.get("statement", {})
        metrics = {m["name"]: m["value"] for m in financial["metrics"]}
        share = financial.get("point_shares")
        # Point-in-time outstanding shares, not weighted-average diluted EPS shares.
        cap = (
            float(frame.close.iloc[-1]) * share["value"]
            if share and 0 <= (cutoff.date() - pd.Timestamp(share["end"]).date()).days <= 150
            else None
        )
        values = {
            "value": statement.get("equity") / cap if cap and statement.get("equity") is not None else None,
            "momentum": float(frame.signal_close.iloc[-22] / frame.signal_close.iloc[-253] - 1)
            if len(frame) >= 253
            else None,
            "quality": metrics.get("roe"),
            "growth": metrics.get("revenue_growth"),
            "low_volatility": float(-frame.signal_close.pct_change().tail(63).std() * np.sqrt(252))
            if len(frame) >= 64
            else None,
            "liquidity": float(np.log((frame.close * frame.volume).tail(20).mean()))
            if len(frame) >= 20
            else None,
        }
        missing = [
            k for k, v in values.items() if weights.get(k, 0) > 0 and (v is None or not np.isfinite(v))
        ]
        if missing:
            unavailable.append({"symbol": symbol, "missing_factors": missing})
            continue
        rows.append(
            {
                "symbol": symbol,
                "sector": None,
                "mode": "historical",
                **values,
                "market_cap_estimate": cap,
                "shares_as_of": share["end"] if share else None,
                "financial_period_end": financial.get("period_end"),
                "financial_available_at": financial.get("available_at"),
            }
        )
    if len(rows) < 3:
        return {
            "status": "unavailable",
            "rows": [],
            "unavailable": unavailable,
            "reason": "선택 팩터를 모두 계산할 실제 종목이 3개 미만입니다.",
        }
    frame = pd.DataFrame(rows).set_index("symbol")
    score = pd.Series(0.0, index=frame.index)
    for key, weight in weights.items():
        if weight <= 0:
            continue
        values = frame[key].clip(frame[key].quantile(0.05), frame[key].quantile(0.95))
        std = values.std(ddof=0)
        frame[key + "_z"] = (values - values.mean()) / std if std > 1e-12 else 0.0
        score += frame[key + "_z"] * weight / sum(weights.values())
    frame["score"], frame["rank"] = score, score.rank(ascending=False, method="min").astype(int)
    return {
        "status": "partial" if unavailable else "ok",
        "rows": frame.reset_index().sort_values("rank").to_dict("records"),
        "unavailable": unavailable,
        "factor_source": "SEC CompanyFacts + Alpaca IEX",
        "price_as_of": view.metadata["as_of"],
        "available_at": cutoff.isoformat(),
        "as_of": cutoff.isoformat(),
        "limitations": [
            "current observed cross-section; not historical factor returns or a validated order strategy",
            "market cap estimate = last regular close × latest observed point common shares (maximum age 150 days)",
            "IEX-only liquidity; 5/95 winsorization and population z-score; ETF lacks company financials",
            "small 4-stock cross-section; no GICS neutralization; missing selected factors exclude a stock",
        ],
    }
