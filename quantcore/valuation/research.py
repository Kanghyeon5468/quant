"""Explicit-assumption valuations and point-in-time company valuation inputs."""
from math import isfinite
from typing import Annotated

from pydantic import BaseModel, Field, FiniteFloat, model_validator
from scipy.optimize import brentq

from quantcore.valuation.dcf import DCFAssumptions, dcf, monte_carlo, sensitivity

Positive = Annotated[FiniteFloat, Field(gt=0)]
Rate = Annotated[FiniteFloat, Field(gt=-1, le=1)]
Discount = Annotated[FiniteFloat, Field(gt=0, le=1)]


class WACCInputs(BaseModel):
    risk_free: Rate
    beta: FiniteFloat
    equity_risk_premium: Annotated[FiniteFloat, Field(ge=0, le=1)]
    pretax_cost_of_debt: Annotated[FiniteFloat, Field(ge=0, le=1)]
    tax_rate: Annotated[FiniteFloat, Field(ge=0, le=1)]
    equity_value: Positive
    debt_value: Annotated[FiniteFloat, Field(ge=0)] = 0


class PerpetuityInputs(BaseModel):
    cash_flow: Positive
    discount: Discount
    growth: Rate

    @model_validator(mode="after")
    def spread(self):
        if self.discount <= self.growth:
            raise ValueError("discount must exceed perpetual growth")
        return self


class ResidualInputs(BaseModel):
    book_value: Positive
    net_income: FiniteFloat
    discount: Discount
    growth: Rate

    @model_validator(mode="after")
    def spread(self):
        if self.discount <= self.growth:
            raise ValueError("discount must exceed residual income growth")
        return self


class Segment(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    enterprise_value: FiniteFloat


class ScenarioRequest(BaseModel):
    wacc: WACCInputs | None = None
    fcfe: PerpetuityInputs | None = None
    dividend: PerpetuityInputs | None = None
    residual: ResidualInputs | None = None
    reverse_dcf_price: Positive | None = None
    dcf_assumptions: DCFAssumptions | None = None
    bull_growth: Annotated[FiniteFloat, Field(ge=-.5, le=.5)] | None = None
    bear_growth: Annotated[FiniteFloat, Field(ge=-.5, le=.5)] | None = None
    segments: list[Segment] = Field(default_factory=list, max_length=50)
    segment_net_debt: FiniteFloat | None = None


def cost_of_capital(inputs):
    equity_cost = inputs.risk_free + inputs.beta * inputs.equity_risk_premium
    debt_cost = inputs.pretax_cost_of_debt * (1 - inputs.tax_rate)
    total = inputs.equity_value + inputs.debt_value
    return {"wacc": (equity_cost*inputs.equity_value + debt_cost*inputs.debt_value)/total,
            "cost_of_equity": equity_cost, "after_tax_cost_of_debt": debt_cost}


def scenarios(request):
    output = {"currency": "USD", "basis": "explicit assumptions", "models": {}}
    models = output["models"]
    if request.wacc:
        models["wacc"] = cost_of_capital(request.wacc)
    for label, inputs in (("fcfe", request.fcfe), ("dividend_discount", request.dividend)):
        if inputs:
            models[label] = {"value": inputs.cash_flow * (1 + inputs.growth)/(inputs.discount-inputs.growth),
                             "basis": "constant growth; next cash flow discounted in perpetuity"}
    if request.residual:
        r = request.residual
        residual = r.net_income - r.discount*r.book_value
        models["residual_income"] = {"equity_value": r.book_value + residual*(1+r.growth)/(r.discount-r.growth)}
    if request.segments:
        if request.segment_net_debt is None:
            raise ValueError("SOTP requires explicit net debt")
        enterprise = sum(segment.enterprise_value for segment in request.segments)
        models["sum_of_parts"] = {"enterprise_value": enterprise, "equity_value": enterprise - request.segment_net_debt}
    if request.dcf_assumptions:
        a = request.dcf_assumptions
        models["fcff"] = {**dcf(a), "sensitivity": sensitivity(a), "monte_carlo": monte_carlo(a)}
        for label, growth in (("bull_case", request.bull_growth), ("bear_case", request.bear_growth)):
            if growth is not None:
                models[label] = {"growth": growth, "per_share": dcf(a.model_copy(update={"growth": growth}))["per_share"]}
        if request.reverse_dcf_price is not None:
            def error(growth):
                return dcf(a.model_copy(update={"growth": growth}))["per_share"] - request.reverse_dcf_price

            lower, upper = error(-.5), error(.5)
            if lower*upper > 0:
                models["reverse_dcf"] = {"status": "unavailable", "reason": "price outside the assumed growth interval"}
            elif (lower == 0 and upper == 0) or not isfinite(lower + upper):
                models["reverse_dcf"] = {"status": "unavailable", "reason": "growth not identified"}
            else:
                models["reverse_dcf"] = {"status": "ok", "implied_revenue_growth": brentq(error, -.5, .5),
                                         "market_price": request.reverse_dcf_price}
    elif request.reverse_dcf_price is not None:
        raise ValueError("reverse DCF requires explicit DCF assumptions")
    if not models:
        raise ValueError("at least one valuation model requires input")
    return output


def company_profile(financial, price, price_at=None):
    statement = financial.get("statement", {})
    shares = (financial.get("point_shares") or {}).get("value")
    cap = price*shares if shares and shares > 0 else None
    debt, cash = statement.get("debt"), statement.get("cash")
    ev = cap + debt - cash if None not in (cap, debt, cash) else None
    metrics = {row["name"]: row["value"] for row in financial.get("metrics", [])}

    def ratio(a, b):
        return a/b if a is not None and b is not None and b > 0 else None

    return {
        "status": financial.get("status", "missing"), "price": price, "price_at": price_at, "currency": "USD",
        "source": financial.get("financial_source"), "source_url": financial.get("source_url"),
        "available_at": financial.get("available_at"), "period_end": financial.get("period_end"),
        "revenue": statement.get("revenue"), "operating_margin": metrics.get("operating_margin"),
        "tax_rate": statement.get("tax_rate"), "shares": shares, "market_cap": cap,
        "net_debt": debt-cash if None not in (debt, cash) else None,
        "multiples": {
            "P/E": ratio(price, statement.get("reported_eps")),
            "P/B": ratio(cap, statement.get("equity")),
            "P/S": ratio(cap, statement.get("revenue")),
            "EV/EBITDA": ratio(ev, metrics.get("ebitda")),
            "EV/EBIT": ratio(ev, statement.get("operating_income")),
            "EV/Sales": ratio(ev, statement.get("revenue")),
            "FCF yield": ratio(metrics.get("free_cash_flow"), cap),
            "Earnings yield": ratio(statement.get("reported_eps"), price),
            "Forward P/E": None, "PEG": None,
        },
        "basis": "current SEC TTM and observed close; forecast/consensus multiples need explicit estimates",
    }
