import numpy as np
from pydantic import BaseModel, Field, FiniteFloat, model_validator


class DCFAssumptions(BaseModel):
    revenue: FiniteFloat = Field(gt=0, default=10e9)
    growth: FiniteFloat = Field(ge=-.5, le=.5, default=.08)
    operating_margin: FiniteFloat = Field(ge=0, le=.8, default=.21)
    tax_rate: FiniteFloat = Field(ge=0, le=1, default=.21)
    depreciation_ratio: FiniteFloat = Field(ge=0, le=.5, default=.03)
    capex_ratio: FiniteFloat = Field(ge=0, le=.5, default=.06)
    working_capital_ratio: FiniteFloat = Field(ge=0, le=1, default=.12)
    wacc: FiniteFloat = Field(gt=0, le=.5, default=.09)
    terminal_growth: FiniteFloat = Field(ge=-.1, le=.1, default=.025)
    net_debt: FiniteFloat = 2e9
    shares: FiniteFloat = Field(gt=0, default=100e6)
    years: int = Field(ge=1, le=20, default=5)

    @model_validator(mode='after')
    def spread(self):
        if self.wacc <= self.terminal_growth:
            raise ValueError('WACC must exceed terminal growth')
        return self


def dcf(a: DCFAssumptions):
    revenue, rows, pv = a.revenue, [], 0.
    for year in range(1, a.years+1):
        previous = revenue
        revenue *= 1+a.growth
        fcff = revenue*a.operating_margin*(1-a.tax_rate)+revenue*a.depreciation_ratio-revenue*a.capex_ratio-(revenue-previous)*a.working_capital_ratio
        discount = (1+a.wacc)**year
        pv += fcff/discount
        rows.append({'year': year, 'revenue': revenue, 'fcff': fcff, 'present_value': fcff/discount})
    next_revenue = revenue*(1+a.terminal_growth)
    terminal_fcff = next_revenue*(a.operating_margin*(1-a.tax_rate)+a.depreciation_ratio-a.capex_ratio)-(next_revenue-revenue)*a.working_capital_ratio
    terminal = terminal_fcff/(a.wacc-a.terminal_growth)
    enterprise = pv+terminal/(1+a.wacc)**a.years
    return {'enterprise_value': enterprise, 'equity_value': enterprise-a.net_debt,
            'per_share': (enterprise-a.net_debt)/a.shares, 'forecast': rows,
            'terminal_value': terminal, 'assumptions': a.model_dump(), 'currency': 'USD',
            'basis': 'explicit user/model assumptions; not a forecast verified against real companies'}


def sensitivity(a):
    return [{'wacc': a.wacc+dw, 'terminal_growth': a.terminal_growth+dg,
             'per_share': dcf(a.model_copy(update={'wacc': a.wacc+dw, 'terminal_growth': a.terminal_growth+dg}))['per_share']}
            for dw in (-.01, 0., .01) for dg in (-.005, 0., .005) if a.wacc+dw > a.terminal_growth+dg and a.wacc+dw > 0]


def monte_carlo(a, samples=2000, seed=42):
    rng = np.random.default_rng(seed)
    values = []
    for growth in np.clip(rng.normal(a.growth, .03, samples), -.5, .5):
        values.append(dcf(a.model_copy(update={'growth': float(growth)}))['per_share'])
    return {'samples': samples, 'seed': seed, 'growth_sigma_assumption': .03,
            'p05': float(np.quantile(values, .05)), 'median': float(np.median(values)), 'p95': float(np.quantile(values, .95))}
