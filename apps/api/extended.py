"""Read-only research endpoints plus pure user-assumption calculators."""
import json
from decimal import Decimal
from pathlib import Path
from typing import Literal

import pandas as pd
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field, FiniteFloat

from quantcore.derivatives.options import implied_volatility
from quantcore.factors.validation import price_factor_validation
from quantcore.fundamentals.advanced import advanced_ratios
from quantcore.fundamentals.sec_facts import normalize
from quantcore.indicators.multi import archived_vwap
from quantcore.indicators.multi import report as technical_report
from quantcore.machine_learning.research import extended_validation
from quantcore.macro.public import report as macro_report
from quantcore.macro.public import usd_to_krw
from quantcore.research.service import json_safe
from quantcore.statistics.timeseries import diagnostics, market_history
from quantcore.strategies.baskets import compare
from quantcore.valuation.research import ScenarioRequest, company_profile, scenarios

router = APIRouter(prefix="/api/research")


class IVRequest(BaseModel):
    price: FiniteFloat = Field(gt=0)
    spot: FiniteFloat = Field(gt=0)
    strike: FiniteFloat = Field(gt=0)
    years: FiniteFloat = Field(gt=0, le=30)
    rate: FiniteFloat = Field(ge=-.2, le=.5)
    kind: Literal["call", "put"] = "call"


def _service(request):
    return request.app.state.service


def _cached(service, metadata, key, calculate):
    if hasattr(service, "view"):
        view = service.view()
        if view.version == metadata["dataset_version"]:
            return service.calculate(view, key, calculate)
    return calculate()


def _snapshot(service, kind="real_equities"):
    if not hasattr(service, "repository"):
        return None
    directory = service.repository.directory / kind
    pointer = directory / "latest.json"
    if not pointer.is_file():
        return None
    return directory / Path(json.loads(pointer.read_text())["snapshot_directory"]).name


@router.get("/macro")
def macro(request: Request):
    service = _service(request)
    directory = getattr(getattr(service, "repository", None), "directory", None)
    return macro_report(directory or request.app.state.market_data_dir)


@router.get("/fx")
def exchange(request: Request, amount: Decimal = Query(max_digits=18, decimal_places=4)):
    return usd_to_krw(macro(request), amount)


@router.post("/valuation")
def valuation_scenarios(body: ScenarioRequest):
    return json_safe(scenarios(body))


@router.get("/valuation/{symbol}")
def valuation_inputs(request: Request, symbol: str):
    service = _service(request)
    frames, meta = market_history(service)
    frame = frames[symbol]
    if not hasattr(service, "information"):
        return {"status": "unavailable", "reason": "SEC valuation inputs require historical mode"}
    financial = service.fundamentals(symbol)
    return json_safe({"symbol": symbol, "mode": meta["mode"],
                      **company_profile(financial, float(frame.close.iloc[-1]), frame.index[-1])})


@router.get("/fundamentals/{symbol}/scores")
def advanced_financials(request: Request, symbol: str):
    service = _service(request)
    frames, _ = market_history(service)
    price = float(frames[symbol].close.iloc[-1])
    snapshot = service.information.snapshot("financials") if hasattr(service, "information") else None
    if not snapshot or not (snapshot[0]/f"companyfacts_{symbol}.json").is_file():
        return {"status": "unavailable", "reason": "company SEC filings are unavailable"}
    folder, manifest = snapshot
    raw = json.loads((folder/f"companyfacts_{symbol}.json").read_text())
    submissions = json.loads((folder/f"submissions_{symbol}.json").read_text())
    filing_dates = submissions["filings"]["recent"]
    acceptance = dict(zip(filing_dates["accessionNumber"], filing_dates["acceptanceDateTime"]))
    normalized = normalize(raw, manifest["collected_at"], acceptance, advanced=True)
    if not normalized["records"]:
        return {"status": "unavailable", "reason": "needs four complete fiscal quarters"}
    current = normalized["records"][-1]
    end = pd.Timestamp(current["period_end"])
    dates = [(abs((end - pd.Timestamp(row["period_end"])).days - 365), row)
             for row in normalized["records"][:-1]
             if 330 <= (end - pd.Timestamp(row["period_end"])).days <= 400]
    prior = min(dates, key=lambda item: item[0])[1] if dates else {}
    shares = normalized["point_shares"][-1]["value"] if normalized["point_shares"] else None
    sic = int(submissions.get("sic", 0) or 0)
    ratios, checks = advanced_ratios(current, prior, price*shares if shares else None, manufacturer=2000 <= sic < 4000)
    return json_safe({"status": "ok" if any(r["value"] is not None for r in ratios) else "unavailable",
                      "symbol": symbol, "metrics": ratios, "piotroski_checks": checks, "period_end": current["period_end"],
                      "prior_period_end": prior.get("period_end"), "available_at": current["available_at"],
                      "source_url": current["source_url"], "basis": "SEC TTM; missing inputs remain null"})


@router.get("/timeseries/{symbol}")
def timeseries(request: Request, symbol: str, peer: str | None = None):
    service = _service(request)
    frames, meta = market_history(service)
    names = [symbol]
    if peer:
        if peer == symbol:
            raise ValueError("choose a separate comparison asset")
        names.append(peer)
    prices = pd.DataFrame({s: frames[s].get("signal_close", frames[s].close) for s in names})
    return json_safe({**meta, **_cached(service, meta, ("extended", "timeseries", symbol, peer),
                                       lambda: diagnostics(prices, symbol, peer))})


@router.get("/options/implied-volatility")
def options_iv(price: FiniteFloat, spot: FiniteFloat, strike: FiniteFloat, years: FiniteFloat, rate: FiniteFloat,
               kind: Literal["call", "put"] = "call"):
    inputs = IVRequest(price=price, spot=spot, strike=strike, years=years, rate=rate, kind=kind)
    vol = implied_volatility(**inputs.model_dump())
    return {"implied_volatility": vol, "basis": "European options, no dividends, explicit price input"}


@router.get("/technical/{symbol}")
def technical(request: Request, symbol: str, timeframe: Literal["daily", "weekly", "monthly"] = "daily"):
    service = _service(request)
    frames, meta = market_history(service)
    if symbol not in frames:
        raise KeyError(symbol)
    if hasattr(service, "indicator_frame"):
        frames = {name: service.indicator_frame(history) for name, history in frames.items()}
    vwap, observed = None, None
    path = _snapshot(service)
    has_raw_minutes = path and json.loads((path/"manifest.json").read_text()).get("raw_pages")
    if timeframe == "daily" and has_raw_minutes:
        vwap, observed = archived_vwap(path, path.name)
    return json_safe({**meta, **_cached(service, meta, ("extended", "technical", symbol, timeframe),
                                       lambda: technical_report(frames, symbol, timeframe, vwap)),
                      "vwap_archive_as_of": observed})


@router.get("/factor-validation")
def factor_validation(request: Request):
    service = _service(request)
    frames, meta = market_history(service)
    return json_safe({**meta, **_cached(service, meta, ("extended", "factors"), lambda: price_factor_validation(frames))})


@router.get("/ml/{symbol}")
def ml_research(request: Request, symbol: str):
    service = _service(request)
    frames, meta = market_history(service)
    frame = frames[symbol]
    return json_safe({**meta, **_cached(service, meta, ("extended", "ml", symbol),
                                       lambda: extended_validation(frame.get("signal_close", frame.close)))})


@router.get("/basket/{method}")
def basket(request: Request,
           method: Literal["cross_sectional_momentum", "pairs_rotation", "volatility_targeting", "etf_allocation"],
           days: int = Query(63, ge=10, le=126)):
    path = _snapshot(_service(request))
    if not path:
        return {"status": "unavailable", "reason": "verified actual IEX minute archive required"}
    return json_safe(compare(path, method, days))


@router.get("/brief")
def brief(request: Request, symbols: str = Query(max_length=60)):
    from quantcore.research.brief import comparative_brief

    selected = list(dict.fromkeys(symbols.split(",")))
    if not 2 <= len(selected) <= 5 or any(not s.isupper() or not s.isalnum() for s in selected):
        raise ValueError("select two to five distinct asset symbols")
    return json_safe(comparative_brief(_service(request), selected))


@router.get("/crypto")
def crypto(request: Request):
    from quantcore.data.providers.coinbase_public import report

    return report(request.app.state.market_data_dir)


@router.get("/factor-neutralization")
def factor_neutralization(request: Request, by: Literal["size", "sic", "size_and_sic"] = "size"):
    from quantcore.data.reference.securities import classification_asof
    from quantcore.factors.validation import neutral_scores

    service = _service(request)
    if not hasattr(service, "information"):
        return {"status": "unavailable", "reason": "requires actual SEC filings and observed market caps"}
    groups = {}
    if by != "size":
        groups, source = classification_asof(None, pd.Timestamp.now(tz="UTC"), data_directory=service.repository.directory)
        if not groups:
            return {"status": "unavailable", "reason": source["reason"]}
    base = service.factors()
    return json_safe({**neutral_scores(base.get("rows", []), groups, size=by != "sic"),
                      "as_of": base.get("available_at"), "by": by,
                      "basis": "cross-sectional study; SEC SIC risk groups when selected"})


@router.get("/imported-markets")
def imported_catalog(request: Request):
    from quantcore.data.providers.research_files import catalog

    return {"status": "ok", "symbols": catalog(request.app.state.market_data_dir)}


@router.get("/imported-markets/{symbol}")
def imported_series(request: Request, symbol: str):
    from quantcore.data.providers.research_files import series

    if not symbol or not all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for c in symbol) or len(symbol) > 20:
        raise ValueError("invalid instrument symbol")
    return series(request.app.state.market_data_dir, symbol)
