"""Self-generated, reproducible data; names are fictional, calendar is synthetic."""
import asyncio
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from quantcore.core.models import Asset, Bar

SYMBOLS = ['QALPHA', 'QBETA', 'QGAMMA', 'QDELTA', 'QEPSILON', 'QZETA']


class DemoProvider:
    source = 'quantcore-synthetic-v1'

    def __init__(self, seed=20261124, periods=780):
        self.seed, self.periods = seed, periods

    def assets(self):
        return [Asset(symbol=s, name=f'Synthetic Company {i+1}', sector=['Technology', 'Industry', 'Consumer'][i % 3],
                      market_cap=(i+1)*10_000_000_000) for i, s in enumerate(SYMBOLS)]

    async def fetch(self, symbol):
        if symbol not in SYMBOLS:
            raise ValueError('unknown synthetic asset')
        await asyncio.sleep(0)
        i = SYMBOLS.index(symbol)
        common = np.random.default_rng(self.seed).normal(.00015, .008, self.periods)
        rng = np.random.default_rng(self.seed+i+1)
        returns = common*(.7+i*.08)+rng.normal(.0001, .009+i*.001, self.periods)
        close = (40+i*25)*np.exp(np.cumsum(returns))
        opening = np.r_[close[0], close[:-1]]*np.exp(rng.normal(0, .002, self.periods))
        ranges = np.abs(rng.normal(.006, .003, self.periods))
        dates = pd.bdate_range('2023-01-02', periods=self.periods, tz='UTC') + pd.Timedelta(hours=21)
        volumes = rng.integers(500_000, 5_000_000, self.periods)
        return [Bar(symbol=symbol, timestamp=t.to_pydatetime(), available_at=t.to_pydatetime(),
                    open=float(o), high=float(max(o, c)*(1+r)), low=float(min(o, c)/(1+r)),
                    close=float(c), volume=int(v), source=self.source, mode='synthetic')
                for t, o, c, r, v in zip(dates, opening, close, ranges, volumes)]

    def fundamentals(self):
        records = []
        for i, symbol in enumerate(SYMBOLS):
            for year in (2022, 2023, 2024):
                revenue = 10e9*(1+i*.3)*(1.08+i*.01)**(year-2022)
                records.append({'symbol': symbol, 'period_end': f'{year}-12-31',
                    'published_at': f'{year+1}-02-15T21:00:00+00:00', 'available_at': f'{year+1}-02-15T21:00:00+00:00',
                    'source': self.source, 'source_url': None, 'mode': 'synthetic', 'currency': 'USD', 'unit': 'USD',
                    'industry': 'nonfinancial', 'revenue': revenue, 'gross_profit': revenue*.45,
                    'operating_income': revenue*.21, 'net_income': revenue*.15, 'depreciation': revenue*.03,
                    'interest_expense': revenue*.01, 'tax_rate': .21, 'operating_cash_flow': revenue*.19,
                    'capex': revenue*.06, 'assets': revenue*1.5, 'equity': revenue*.8,
                    'debt': revenue*.3, 'cash': revenue*.1, 'current_assets': revenue*.6,
                    'current_liabilities': revenue*.3, 'shares': 100e6*(1+i*.1), 'retained_earnings': revenue*.4})
        return records


def default_as_of():
    return datetime(2026, 1, 1, tzinfo=timezone.utc)
