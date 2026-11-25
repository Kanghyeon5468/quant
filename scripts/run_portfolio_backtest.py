"""Replay the frozen authorized minute data with the same policy as paper. No network or orders."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from quantcore.backtesting.portfolio import load_minutes, replay
from quantcore.paper.guard import settings
from quantcore.research.real_equities import latest_snapshot
from quantcore.risk.limits import RiskLimits
from quantcore.strategies.orders import OrderPolicy


def run(root):
    root = Path(root)
    snapshot = latest_snapshot(root)
    daily, minutes, manifest = load_minutes(snapshot)
    policy = settings(root/'configs', 'order_policy.json', OrderPolicy)
    limits = settings(root/'configs', 'risk_limits.json', RiskLimits)
    code = hashlib.sha256(b''.join((root/name).read_bytes() for name in [
        'quantcore/backtesting/portfolio.py', 'quantcore/risk/limits.py', 'quantcore/strategies/orders.py',
        'quantcore/strategies/base.py'])).hexdigest()
    metadata = {'executed_at': datetime.now(timezone.utc).isoformat(), 'mode': 'historical',
                'snapshot_id': snapshot.name, 'snapshot_hashes': manifest['hashes'], 'code_sha256': code,
                'regular_minute_rows': len(minutes), 'raw_pages_verified': len(manifest['raw_pages']),
                'budget': 100000, 'symbols': list(manifest['symbols']), 'evaluation_sessions': 252,
                'source': 'Alpaca IEX observed regular-session minute OHLCV',
                'cost_basis': 'same order policy as paper; broker P&L and cost estimates remain separate',
                'limitations': ['OHLC limit touches and 1% observed minute-volume cap; not NBBO queue or random Alpaca matching',
                  'no after-hours, dividends, interest, taxes, delisted-universe correction or historical revision archive',
                  'unknown sectors grouped as UNCLASSIFIED with 40% cap; no ETF look-through',
                  'no forced liquidation: risk blocks buys/cancels own pending buys; price losses may exceed thresholds',
                  'drawdown halt latches until explicit operator reset; no reset during historical evaluation',
                  'fixed universe and unchanged default limits, no performance optimization',
                  'marks carried only between observed minutes; risk checked after completed bars every 5 minutes']}
    results = {}
    zero = policy.model_copy(update={'commission_bps': 0., 'slippage_bps': 0., 'spread_bps': 0., 'impact_bps': 0.})
    for name, strategy, risk, costs in [
        ('momentum_unrestricted_net', 'momentum', False, policy),
        ('momentum_risk_net', 'momentum', True, policy),
        ('momentum_risk_gross', 'momentum', True, zero),
        ('buy_hold_slots_net', 'buy_hold', False, policy)]:
        print(f'Replaying {name}', flush=True)
        results[name] = replay(daily, minutes, strategy=strategy, risk_enabled=risk, policy=costs, limits=limits)
        print(json.dumps({'scenario': name, **results[name]['metrics']}), flush=True)
    report = {'metadata': metadata, 'results': results}
    out = root/'artifacts/portfolio_replay'
    out.mkdir(parents=True, exist_ok=True)
    (out/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    public = {'metadata': metadata, 'results': {name: {k: value for k, value in result.items()
                if k in ('metrics', 'curve', 'audit', 'config', 'risk_events')} for name, result in results.items()}}
    (root/'docs/portfolio_backtest_results.json').write_text(json.dumps(public, indent=2, allow_nan=False)+'\n')
    first = next(iter(results.values()))['curve']
    print(json.dumps({'period': [first[0]['session'], first[-1]['session']], 'report': str(out/'report.json')}))
    return public


if __name__ == '__main__':
    run(Path(__file__).resolve().parents[1])
