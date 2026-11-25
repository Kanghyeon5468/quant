"""Actual market adapter for the same Python analysis engines; never holds API keys."""
import asyncio

import pandas as pd

from quantcore.backtesting.engine import ExecutionConfig, backtest
from quantcore.data.calendar import sessions
from quantcore.data.storage.market import MarketRepository
from quantcore.indicators.technical import technical
from quantcore.information.service import InformationService, real_factors
from quantcore.machine_learning.validation import walk_forward
from quantcore.monitoring.metrics import Metrics
from quantcore.portfolio.optimization import optimize
from quantcore.risk.analytics import risk_report
from quantcore.statistics.research import statistical_report
from quantcore.strategies.base import STRATEGIES, Momentum

NAMES = {'AAPL': 'Apple', 'MSFT': 'Microsoft', 'NVDA': 'NVIDIA', 'TSLA': 'Tesla', 'SPY': 'SPDR S&P 500 ETF'}


class ActualResearchService:
    mode = 'historical'

    def __init__(self, directory):
        self.repository, self.metrics = MarketRepository(directory), Metrics()
        self._version, self._cache = None, {}
        self.information = InformationService(directory)

    async def bootstrap(self):
        await asyncio.to_thread(self.repository.load)

    def close(self):
        pass

    def view(self):
        view = self.repository.load()
        if view.version != self._version:
            self._cache, self._version = {}, view.version
        return view

    def calculate(self, view, key, function):
        key = (view.version, *key)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        with self.metrics.measure(key[1]):
            value = function()
        if self._version == view.version:
            if len(self._cache) >= 100:
                self._cache.clear()
            self._cache[key] = value
        return value

    def frame(self, view, symbol):
        if symbol not in view.frames:
            raise KeyError('unknown actual asset')
        return view.frames[symbol]

    def quality(self, frame):
        if frame.empty:
            return {'score': 0, 'status': 'missing', 'rows': 0, 'calendar': 'XNYS'}
        expected = sessions(frame.iloc[0].session, frame.iloc[-1].session)
        missing = len(set(expected.index)-set(frame.session))
        return {'score': max(0., 1-missing/len(expected)), 'status': 'ok' if not missing else 'review',
                'rows': len(frame), 'missing_exchange_sessions': missing, 'calendar': 'XNYS',
                'feed_scope': 'IEX single exchange; not consolidated SIP'}

    def overview(self):
        view = self.view()
        assets = []
        for symbol, frame in view.frames.items():
            assets.append({'symbol': symbol, 'name': NAMES[symbol], 'asset_class': 'etf' if symbol == 'SPY' else 'equity',
                'sector': None, 'market_cap': None, 'currency': 'USD', 'price': float(frame.close.iloc[-1]),
                'change': float(frame.signal_close.pct_change().iloc[-1]), 'volume': int(frame.volume.iloc[-1]),
                'quality': self.quality(frame)['score']})
        today = pd.Timestamp.now(tz='UTC')
        expected = sessions(today.date()-pd.Timedelta(days=15), today.date(), today)
        return {'name': 'QuantCore', **view.metadata, 'execution_mode': 'research', 'assets': assets,
            'stale': bool(len(expected) and expected.index[-1] > max(f.session.iloc[-1] for f in view.frames.values())),
            'incremental': {'nodes': 0, 'computations': 0, 'cache_hits': 0},
            'limitations': ['completed regular-session bars, not streaming quotes', 'IEX single exchange',
                            'SEC financials and news are separately timed observations; LLM/earnings transcripts unavailable', 'analysis API never submits orders']}

    def prices(self, symbol, limit=252, as_of=None):
        view = self.view()
        frame = self.frame(view, symbol)
        if as_of is not None:
            stamp = pd.Timestamp(as_of)
            if stamp.tzinfo is None:
                raise ValueError('as_of must be timezone-aware')
            frame = frame[frame.available_at <= stamp]
        return {**view.metadata, 'symbol': symbol, 'as_of': frame.index.max().isoformat() if len(frame) else None,
                'prices': frame.tail(limit).reset_index().to_dict('records'), 'quality': self.quality(frame)}

    def indicator_frame(self, frame):
        adjusted = frame.copy()
        cumulative = frame.signal_close/frame.close
        factor = cumulative/cumulative.iloc[-1]
        for field in ('open', 'high', 'low', 'close'):
            adjusted[field] = frame[field]*factor
        adjusted['volume'] = frame.volume/factor
        return adjusted

    def indicators(self, symbol):
        view = self.view()
        def compute():
            frame = self.indicator_frame(self.frame(view, symbol))
            result = technical(frame)
            result['sma_60'] = frame.close.rolling(60).mean()
            result['close'] = frame.close
            return {**view.metadata, 'symbol': symbol, 'price_unit': 'USD/share',
                    'price_basis': 'split-adjusted to latest visible session units',
                    'values': result.tail(252).reset_index().to_dict('records')}
        return self.calculate(view, ('indicators', symbol), compute)

    def fundamentals(self, symbol, as_of=None):
        view = self.view()
        self.frame(view, symbol)
        return {**view.metadata, **self.information.financials(symbol, as_of)}

    def factors(self, weights=None, sector_neutral=False):
        view = self.view()
        return {**view.metadata, **real_factors(view, self.information, weights, sector_neutral)}

    def information_report(self, symbol=None, as_of=None):
        if symbol:
            self.frame(self.view(), symbol)
        return self.information.report(symbol, as_of)

    def backtest(self, symbol, strategy):
        view = self.view()
        if strategy not in STRATEGIES:
            raise ValueError('unsupported strategy')
        frame = self.frame(view, symbol)
        if len(frame) < 313:
            return {**view.metadata, 'symbol': symbol, 'status': 'insufficient_history',
                    'reason': '252개 평가 세션과60개 사전 세션 이상의 실제 이력이 필요합니다.'}
        return self.calculate(view, ('backtest', symbol, strategy), lambda: {
            **backtest(frame, STRATEGIES[strategy](), ExecutionConfig(), view.actions[symbol]),
            **view.metadata, 'symbol': symbol,
            'scope': 'independent asset research simulation; different sizing/execution from paper account'})

    def returns(self):
        return pd.DataFrame({s: f.signal_close.pct_change() for s, f in self.view().frames.items()}).dropna().tail(252)

    def portfolio(self, method='minimum_variance', max_weight=.4):
        view = self.view()
        def compute():
            returns = pd.DataFrame({s: f.signal_close.pct_change() for s, f in view.frames.items()}).dropna().tail(252)
            result = optimize(returns, method, max_weight)
            risk = risk_report(returns, list(result['weights'].values()))
            risk.update(mode='historical', horizon='one XNYS regular session')
            return {**result, **view.metadata, 'risk': risk,
                    'scope': 'in-sample research allocation, not current paper holdings; price returns exclude cash dividends'}
        return self.calculate(view, ('portfolio', method, max_weight), compute)

    def machine_learning(self, symbol):
        view = self.view()
        frame = self.frame(view, symbol).copy()
        if len(frame) < 331:
            return {**view.metadata, 'symbol': symbol, 'status': 'insufficient_history',
                    'reason': '실제 walk-forward 학습/평가 이력이 부족합니다.', 'metrics': [], 'splits': []}
        frame['close'] = frame.signal_close
        return self.calculate(view, ('ml', symbol), lambda: {**walk_forward(frame), **view.metadata,
            'symbol': symbol, 'scope': 'price-return model evaluation only; not a paper order signal'})

    def statistics(self):
        view = self.view()
        returns = pd.DataFrame({s: f.signal_close.pct_change() for s, f in view.frames.items()}).dropna().tail(252)
        return self.calculate(view, ('statistics',), lambda: {**statistical_report(returns), **view.metadata})

    def signal(self, symbol):
        view = self.view()
        frame = self.frame(view, symbol).copy()
        frame['close'] = frame.signal_close
        target = float(Momentum().targets(frame).iloc[-1])
        current_factor = frame.signal_close.iloc[-1]/self.frame(view, symbol).close.iloc[-1]
        return {**view.metadata, 'symbol': symbol, 'strategy': 'momentum',
                'signal': 'buy' if target else 'cash', 'target_weight_within_slot': target,
                'reference_close': float(self.frame(view, symbol).close.iloc[-1]),
                'sma_60': float(frame.close.rolling(60).mean().iloc[-1]/current_factor),
                'signal_available_at': frame.available_at.iloc[-1].isoformat(), 'order_submission': False}

    def research_report(self, symbol):
        return {**self.signal(symbol), 'kind': 'deterministic_calculation_report', 'llm_enabled': False,
                'financial_status': self.information.financials(symbol)['status'], 'limitations': ['price-based signal; no news/filings/earnings model']}

    def monitoring(self):
        view = self.view()
        return {**self.metrics.report(), **view.metadata, 'cache_entries': len(self._cache),
            'capabilities': {'actual_market_data': True, 'streaming_quotes': False, 'exchange_calendar': True,
                             'actual_fundamentals': bool(self.information.snapshot('financials')), 'actual_13f': bool(self.information.snapshot('institutions')), 'actual_news': bool(self.information.snapshot('news')), 'earnings_calls': False, 'order_routing': False, 'llm': False,
                             'usd': True, 'krw_conversion': False}}
