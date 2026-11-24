"""Application service composes independent analytics; it never submits orders."""
from functools import lru_cache

import numpy as np
import pandas as pd

from quantcore.backtesting.engine import backtest
from quantcore.core.models import Event
from quantcore.data.ingestion.pipeline import ingest
from quantcore.data.providers.demo import DemoProvider
from quantcore.data.storage.store import Store
from quantcore.data.validation.quality import quality_report
from quantcore.events.bus import EventBus
from quantcore.factors.engine import factor_scores
from quantcore.fundamentals.analysis import analyze
from quantcore.incremental.graph import Graph
from quantcore.indicators.technical import technical
from quantcore.machine_learning.validation import walk_forward
from quantcore.monitoring.metrics import Metrics
from quantcore.portfolio.optimization import optimize
from quantcore.risk.analytics import risk_report
from quantcore.strategies.base import STRATEGIES


class ResearchService:
    def __init__(self, directory):
        self.store = Store(directory)
        self.metrics = Metrics()
        self.graph = Graph()
        self.bus = EventBus()
        self.bus.subscribe('prices.batch', self.on_prices)

    async def on_prices(self, event):
        with self.metrics.measure('event_processing'):
            values = event.payload['prices']
            if any(s not in self.frames or not np.isfinite(v) or v <= 0 for s, v in values.items()):
                raise ValueError('invalid event price')
            self.graph.update(values)

    async def bootstrap(self):
        provider = DemoProvider()
        with self.metrics.measure('ingestion'):
            outcome = await ingest(provider, self.store)
            if outcome['errors']:
                raise RuntimeError('demo ingestion failed')
            self.store.save_fundamentals(provider.fundamentals())
            self.manifest = self.store.export_parquet()
        self.assets = self.store.asset_list()
        self.frames = {a['symbol']: self.store.prices(a['symbol']) for a in self.assets}
        self.as_of = max(f.index.max() for f in self.frames.values())
        self.version = self.manifest['sha256'][:12]
        for symbol, frame in self.frames.items():
            self.graph.input(symbol, float(frame.close.iloc[-2]))
            self.graph.derive(symbol+'_value', [symbol], lambda price: price*10)
        names = [s+'_value' for s in self.frames]
        self.graph.derive('demo_portfolio_value', names, lambda *values: sum(values))
        self.graph.stabilize()
        await self.bus.publish(Event(kind='prices.batch', version=1, timestamp=self.as_of.to_pydatetime(),
                                    payload={'prices': {s: float(f.close.iloc[-1]) for s, f in self.frames.items()}}))
        await self.bus.drain()
        if self.bus.failures:
            raise RuntimeError('initial price event failed')
        return outcome

    def require_asset(self, symbol):
        if symbol not in self.frames:
            raise KeyError('unknown asset')
        return self.frames[symbol]

    def overview(self):
        rows = []
        for asset in self.assets:
            frame = self.frames[asset['symbol']]
            rows.append({**asset, 'price': float(frame.close.iloc[-1]),
                'change': float(frame.close.iloc[-1]/frame.close.iloc[-2]-1),
                'volume': int(frame.volume.iloc[-1]), 'quality': quality_report(frame)['score']})
        return {'name': 'QuantCore', 'mode': 'synthetic', 'execution_mode': 'research',
            'as_of': self.as_of.isoformat(), 'source': 'quantcore-synthetic-v1', 'currency': 'USD',
            'dataset_version': self.version, 'rows': self.manifest['rows'], 'assets': rows,
            'incremental': {'nodes': len(self.graph.nodes), 'computations': self.graph.computations,
                            'cache_hits': self.graph.cache_hits,
                            'demo_portfolio_value': self.graph.get('demo_portfolio_value')},
            'limitations': ['fictional companies and synthetic prices', 'no external market feeds or order routing']}

    def prices(self, symbol, limit=252, as_of=None):
        self.require_asset(symbol)
        frame = self.store.prices(symbol, as_of) if as_of else self.frames[symbol]
        return {'symbol': symbol, 'mode': 'synthetic', 'currency': 'USD',
            'source': 'quantcore-synthetic-v1', 'as_of': str(frame.index.max()) if len(frame) else None,
            'prices': frame.tail(limit).reset_index().to_dict('records'), 'quality': quality_report(frame)}

    @lru_cache(maxsize=12)
    def indicators(self, symbol):
        frame = self.require_asset(symbol)
        result = technical(frame)
        return {'symbol': symbol, 'source': 'quantcore-synthetic-v1', 'mode': 'synthetic',
                'as_of': self.as_of.isoformat(), 'currency': 'USD', 'price_unit': 'USD/share',
                'oscillator_units': 'RSI/ADX/stochastic: 0-100; volatility: annualized fraction; ROC: percent',
                'values': result.tail(252).reset_index().to_dict('records')}

    def fundamentals(self, symbol, as_of=None):
        self.require_asset(symbol)
        return analyze(self.store.fundamentals(symbol, as_of or self.as_of))

    def factors(self, weights=None, sector_neutral=False):
        return {'as_of': self.as_of.isoformat(), 'source': 'quantcore-synthetic-v1', 'mode': 'synthetic',
                'unit': 'dimensionless cross-sectional z-score', 'currency': 'USD',
                'rows': factor_scores(self.store, self.as_of, weights, sector_neutral)}

    @lru_cache(maxsize=24)
    def backtest(self, symbol, strategy):
        frame = self.require_asset(symbol)
        if strategy not in STRATEGIES:
            raise ValueError('unsupported strategy')
        with self.metrics.measure('backtest'):
            result = backtest(frame, STRATEGIES[strategy]())
        result.update(symbol=symbol, currency='USD', source='quantcore-synthetic-v1', dataset_version=self.version)
        return result

    def returns(self):
        return pd.DataFrame({s: f.close.pct_change() for s, f in self.frames.items()}).dropna().tail(252)

    @lru_cache(maxsize=12)
    def portfolio(self, method='minimum_variance', max_weight=.4):
        returns = self.returns()
        with self.metrics.measure('portfolio'):
            result = optimize(returns, method, max_weight)
            result['risk'] = risk_report(returns, list(result['weights'].values()))
        result.update(as_of=self.as_of.isoformat(), source='quantcore-synthetic-v1', mode='synthetic')
        return result

    @lru_cache(maxsize=6)
    def machine_learning(self, symbol):
        with self.metrics.measure('ml_walk_forward'):
            return walk_forward(self.require_asset(symbol))

    def research_report(self, symbol):
        facts = self.fundamentals(symbol)
        metrics = {m['name']: m for m in facts['metrics']}
        result = self.backtest(symbol, 'momentum')
        return {'kind': 'deterministic_calculation_report', 'llm_enabled': False, 'mode': 'synthetic',
            'symbol': symbol, 'as_of': self.as_of.isoformat(),
            'observations': [{'text': name, 'value': metrics[name]['value'], 'evidence': metrics[name]}
                             for name in ('revenue_growth', 'roe', 'free_cash_flow')],
            'strategy_metrics': result['metrics'], 'counter_hypothesis': 'synthetic patterns may not persist in real markets',
            'limitations': ['not a generative AI assistant', 'no external company facts or investment recommendations']}

    def monitoring(self):
        return {**self.metrics.report(), 'mode': 'synthetic', 'dataset_version': self.version,
            'storage': self.store.parquet_summary(), 'backtest_cache': self.backtest.cache_info()._asdict(),
            'dag': {'nodes': len(self.graph.nodes), 'dirty': len(self.graph.dirty), 'computations': self.graph.computations,
                    'cache_hits': self.graph.cache_hits},
            'event_queue_depth': self.bus.queue.qsize(), 'event_errors': len(self.bus.failures),
            'capabilities': {'demo_data': True, 'live_data': False, 'order_routing': False, 'llm': False,
                             'usd': True, 'krw_conversion': False, 'exchange_calendar': False}}


def json_safe(value):
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value
