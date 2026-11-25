"""Actual-input experiment using the existing fixed strategies and execution engine."""
import hashlib
import json
import platform
from datetime import datetime, timezone
from decimal import Decimal
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd

from quantcore.backtesting.engine import ExecutionConfig, backtest, simulate
from quantcore.data.providers.alpaca import load_snapshot
from quantcore.research.service import json_safe
from quantcore.strategies.base import STRATEGIES


def latest_snapshot(root):
    path = Path(root)/'datasets/real_equities/latest.json'
    if not path.exists():
        raise FileNotFoundError('Actual prices are absent. Run scripts/collect_real_equities.py with authorized credentials; no demo fallback.')
    target = Path(json.loads(path.read_text())['snapshot_directory'])
    if not target.is_dir():
        raise FileNotFoundError('The frozen actual-data snapshot is not on this machine. Collect an authorized local snapshot.')
    return target


def ledger_audit(frame, result):
    cash = Decimal(str(result['config']['initial_cash']))
    fills = pd.DataFrame(result['fills'])
    if not fills.empty:
        fills['at'] = pd.to_datetime(fills.timestamp, utc=True)
    for row in result['curve']:
        stamp = pd.Timestamp(row['timestamp'])
        cash += Decimal(row['corporate_action_cash'])
        if not fills.empty:
            today = fills[fills['at'].dt.date == stamp.date()]
            for fill in today.to_dict('records'):
                cash -= (1 if fill['side'] == 'buy' else -1)*Decimal(str(fill['notional']))+Decimal(str(fill['commission']))
        if cash != Decimal(row['cash']) or cash < 0 or row['quantity'] < 0:
            raise AssertionError('historical cash/inventory reconciliation failed')
        expected = float(cash+Decimal(row['quantity'])*Decimal(str(frame.loc[stamp, 'close']))+Decimal(row['dividend_receivable']))
        if not np.isclose(expected, row['equity'], rtol=0, atol=1e-8):
            raise AssertionError('historical NAV reconciliation failed')
    return True


def run_actual(snapshot, config=None, verify_future=True):
    config = config or ExecutionConfig()
    market, actions, manifest = load_snapshot(snapshot)
    if manifest['source'] != 'alpaca-iex-regular-1min' or manifest['feed'] != 'iex':
        raise ValueError('unexpected historical source')
    frames = {s: group.set_index('timestamp').sort_index() for s, group in market.groupby('symbol')}
    results, summary, audits = {}, [], []
    for symbol, frame in frames.items():
        if len(frame) <= config.evaluation_bars+60:
            raise ValueError('insufficient pre-evaluation warmup')
        for name in ('momentum', 'mean_reversion', 'buy_hold'):
            result = backtest(frame, STRATEGIES[name](), config, actions[symbol])
            if result['mode'] != 'historical':
                raise AssertionError('actual data mislabeled as synthetic')
            ledger_audit(frame, result)
            for fill in result['fills']:
                if pd.Timestamp(fill['signal_at']) >= pd.Timestamp(fill['timestamp']):
                    raise AssertionError('signal entered its own past')
            if verify_future:
                changed = frame.copy()
                cutoff = frame.iloc[-10].execution_open
                changed.loc[changed.index[-10]:, ['open', 'high', 'low', 'close', 'signal_close']] *= 1.25
                future = simulate(changed, STRATEGIES[name](), config, actions[symbol])
                def prefix(item):
                    return [fill for fill in item['fills'] if pd.Timestamp(fill['timestamp']) < cutoff]
                if prefix(result) != prefix(future):
                    raise AssertionError('future quote mutation changed historical fills')
            results[symbol, name] = result
            summary.append({'symbol': symbol, 'strategy': name, **result['metrics'],
                'gross_total_return': result['gross_metrics']['total_return'],
                'benchmark_total_return': result['benchmark_metrics']['total_return'],
                'dividend_cash_received': sum(float(r['dividend_cash_paid']) for r in result['curve']),
                'dividend_receivable_at_end': float(result['curve'][-1]['dividend_receivable'])})
            audits.append({'symbol': symbol, 'strategy': name, 'mode': result['mode'], 'period': result['period'],
                'sessions': len(result['curve']), 'signal_before_execution': True, 'cash_inventory_nav_reconciled': True,
                'future_mutation_invariant': verify_future})
    package = Path(__file__).resolve().parents[1]
    code_files = [package/name for name in ('backtesting/engine.py', 'strategies/base.py',
                  'data/calendar.py', 'data/providers/alpaca.py', 'research/real_equities.py')]
    code_hash = hashlib.sha256(b''.join(path.name.encode()+path.read_bytes() for path in code_files)).hexdigest()
    metadata = {'executed_at': datetime.now(timezone.utc).isoformat(), 'data_mode': 'historical',
        'code_sha256': code_hash, 'environment': {'python': platform.python_version(),
            'packages': {name: version(name) for name in ('numpy', 'pandas', 'exchange-calendars', 'pyarrow')}},
        'snapshot_id': Path(snapshot).name, 'snapshot_hashes': manifest['hashes'], 'source': manifest['source'],
        'feed': 'iex; one exchange, not consolidated SIP', 'market_sessions': manifest['sessions'],
        'minute_rows_downloaded': manifest['minute_rows_downloaded'], 'regular_minute_rows': manifest['regular_minute_rows'],
        'daily_rows': manifest['daily_rows'], 'collected_at': manifest['collected_at'],
        'price_period': {'start': manifest['start'], 'end': manifest['end']}, 'config': config.model_dump(),
        'opening_delay_max_seconds': manifest['opening_delay_max_seconds'], 'closing_age_max_seconds': manifest['closing_age_max_seconds'],
        'actions_counts': manifest['actions_counts'], 'dividend_cash_assumption': 'first XNYS session after payable date; receivable from ex-date',
        'effective_action_counts': {symbol: {'dividends': sum(a.kind == 'dividend' for a in items),
                                           'splits': sum(a.kind == 'split' for a in items)} for symbol, items in actions.items()},
        'signal_price_basis': 'raw close multiplied by cumulative splits effective by that session only',
        'performance_claim': 'historical-data trading simulation; not live account profit',
        'limitations': ['current chosen large-cap universe; selection/survivorship bias not eliminated',
                        'historical archive fetched now; original revision/collection latency unavailable',
                        'first observed regular-session minute open is a modeled execution reference, not a guaranteed fill',
                        'costs/market impact and prior-day IEX-volume participation are assumptions, not order-book reconstruction',
                        'no tax, cash interest, borrow, shorting, financing or automatic broker orders']}
    return frames, actions, results, pd.DataFrame(summary), metadata, pd.DataFrame(audits)


def export_actual(root, snapshot, config=None):
    root = Path(root)
    frames, actions, results, summary, metadata, audits = run_actual(snapshot, config)
    digest = hashlib.sha256(json.dumps({'input': metadata['snapshot_hashes'], 'config': metadata['config'],
                                        'code': metadata['code_sha256']}, sort_keys=True).encode()).hexdigest()[:12]
    directory = root/'artifacts/real_equities'/digest
    directory.mkdir(parents=True, exist_ok=True)
    summary.to_csv(directory/'metrics.csv', index=False)
    audits.to_csv(directory/'validation.csv', index=False)
    pd.concat([pd.DataFrame(r['curve']).assign(symbol=s, strategy=n) for (s,n),r in results.items()]).to_csv(directory/'curves.csv', index=False)
    trades = [pd.DataFrame(r['fills']).assign(symbol=s, strategy=n) for (s,n),r in results.items() if r['fills']]
    if trades:
        pd.concat(trades, ignore_index=True).to_csv(directory/'fills.csv', index=False)
    metadata['result_directory'] = str(directory.relative_to(root))
    (directory/'experiment.json').write_text(json.dumps(json_safe(metadata), indent=2)+'\n')
    report = {'metadata': metadata, 'results': summary.to_dict('records'), 'validation': audits.to_dict('records')}
    (root/'docs/real_equity_results.json').write_text(json.dumps(json_safe(report), indent=2)+'\n')
    return report
