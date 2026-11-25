"""Predeclared chronological selection, continuous OOS portfolio and reserved final window."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from quantcore.backtesting.portfolio import load_minutes, replay
from quantcore.paper.guard import settings
from quantcore.research.real_equities import latest_snapshot
from quantcore.risk.limits import RiskLimits
from quantcore.strategies.orders import OrderPolicy


def window_metrics(curve, days, initial=100000):
    frame = pd.DataFrame(curve).set_index('session')
    if len(days) < 2 or not set(days).issubset(frame.index):
        raise ValueError('evaluation window needs >=2 observed sessions')
    first = frame.index.get_loc(days[0])
    baseline = float(frame.equity.iloc[first-1]) if first else initial
    values = np.r_[baseline, frame.loc[days].equity.to_numpy(dtype=float)]
    returns = values[1:]/values[:-1]-1
    std = returns.std(ddof=1)
    return {'start': days[0], 'end': days[-1], 'sessions': len(days),
            'total_return': float(values[-1]/baseline-1),
            'max_drawdown': float((values/np.maximum.accumulate(values)-1).min()),
            'annualized_volatility': float(std*np.sqrt(252)),
            'sharpe': float(returns.mean()/std*np.sqrt(252)) if std > 1e-12 else 0.}


def select_candidate(curves, training_days, validation_days, available_at, cutoff):
    cut = pd.Timestamp(cutoff)
    if cut.tzinfo is None or training_days[-1] >= validation_days[0]:
        raise ValueError('training must precede validation with an aware cutoff')
    if any(pd.Timestamp(available_at[day]) > cut for day in training_days+validation_days):
        raise ValueError('selection includes unavailable future observations')
    rows = []
    for name, curve in curves.items():
        training = window_metrics(curve, training_days)
        validation = window_metrics(curve, validation_days)
        rows.append({'candidate': name, 'training': training, 'validation': validation})
    selected = max(rows, key=lambda r: r['validation']['sharpe'])['candidate']
    return {'selected': selected, 'selection_available_at': cut.isoformat(), 'candidates': rows,
            'training': [training_days[0], training_days[-1]],
            'validation': [validation_days[0], validation_days[-1]]}


def split_windows(days, plan):
    holdout = plan['final_holdout_sessions']
    dev_end = len(days)-holdout
    first = plan['minimum_training_sessions']+plan['validation_sessions']
    if holdout < 2 or first+plan['test_sessions'] > dev_end:
        raise ValueError('insufficient history for predeclared chronological windows')
    folds = []
    for start in range(first, dev_end-plan['test_sessions']+1, plan['test_sessions']):
        train_end = start-plan['validation_sessions']
        folds.append({'kind': 'walk_forward', 'training': days[:train_end],
            'validation': days[train_end:start], 'test': days[start:start+plan['test_sessions']]})
    if folds[-1]['test'][-1] != days[dev_end-1]:
        raise ValueError('plan would leave an untested development gap')
    folds.append({'kind': 'reserved_holdout', 'training': days[:dev_end-plan['validation_sessions']],
                  'validation': days[dev_end-plan['validation_sessions']:dev_end], 'test': days[dev_end:]})
    return folds


def paired_bootstrap(selected, baseline, seed):
    a, b = np.asarray(selected), np.asarray(baseline)
    if len(a) != len(b) or len(a) < 10:
        raise ValueError('paired return histories must align')
    rng = np.random.default_rng(seed)
    differences = []
    block = 5
    for _ in range(2000):
        starts = rng.integers(0, len(a), size=int(np.ceil(len(a)/block)))
        indices = np.concatenate([(np.arange(block)+s) % len(a) for s in starts])[:len(a)]
        differences.append(np.prod(1+a[indices])-np.prod(1+b[indices]))
    return {'method': 'paired circular 5-session block bootstrap; 2000 seeded samples',
            'difference_total_return_95_interval': np.quantile(differences, [.025,.975]).tolist(),
            'scope': 'sample uncertainty only; no selection-bias or untouched-data guarantee'}


def run_validation(root):
    root = Path(root)
    raw_plan = (root/'configs/walk_forward.json').read_bytes()
    plan = json.loads(raw_plan)
    directory = root/'artifacts/walk_forward'
    directory.mkdir(parents=True, exist_ok=True)
    (directory/'frozen_plan.json').write_bytes(raw_plan)
    snapshot = latest_snapshot(root)
    daily, minutes, manifest = load_minutes(snapshot)
    all_days = sorted(daily.session.unique())
    days = all_days[plan['warmup_sessions']:]
    windows = split_windows(days, plan)
    development_end = windows[-1]['validation'][-1]
    development_days = [d for d in days if d <= development_end]
    available = daily.groupby('session').available_at.max().to_dict()
    policy = settings(root/'configs', 'order_policy.json', OrderPolicy)
    limits = settings(root/'configs', 'risk_limits.json', RiskLimits)
    # Today's sourced classifications are not a verified historical vintage.
    limits = limits.model_copy(update={'sectors': {}})
    candidates, curves = {}, {}
    for name in plan['candidates']:
        print('Development replay: '+name, flush=True)
        result = replay(daily[daily.session <= development_end], minutes[minutes.session <= development_end],
            strategy=name, budget=plan['budget_usd'], evaluation_sessions=len(development_days), policy=policy, limits=limits)
        candidates[name], curves[name] = result, result['curve']
    decisions, schedule = [], {}
    for i, window in enumerate(windows):
        selection = select_candidate(curves, window['training'], window['validation'], available,
                                     available[window['validation'][-1]])
        opening = daily.loc[daily.session == window['test'][0], 'session_open'].min()
        if pd.Timestamp(selection['selection_available_at']) >= opening:
            raise AssertionError('strategy was selected after its first OOS execution')
        decision = {**selection, 'fold': i+1, 'kind': window['kind'],
                    'test': [window['test'][0], window['test'][-1]], 'test_sessions': len(window['test'])}
        decisions.append(decision)
        schedule.update(dict.fromkeys(window['test'], decision['selected']))
        print(json.dumps({k:decision[k] for k in ['fold','kind','selected','training','validation','test']}), flush=True)
    oos_days = sorted(schedule)
    results = {}
    for name, strategy, chosen, costs in [
        ('selected_oos', 'momentum', schedule, policy),
        ('fixed_momentum_60', 'momentum', None, policy),
        ('always_active_slots', 'buy_hold', None, policy),
        ('selected_double_cost', 'momentum', schedule, policy.model_copy(update={
            'commission_bps': policy.commission_bps*2, 'slippage_bps': policy.slippage_bps*2,
            'spread_bps': policy.spread_bps*2, 'impact_bps': policy.impact_bps*2}))]:
        print('Continuous OOS replay: '+name, flush=True)
        results[name] = replay(daily, minutes, strategy=strategy, budget=plan['budget_usd'],
            evaluation_sessions=len(oos_days), policy=costs, limits=limits, strategy_by_day=chosen)
        print(json.dumps({'scenario':name, **results[name]['metrics']}), flush=True)
    for decision, window in zip(decisions, windows):
        decision['oos'] = {name:window_metrics(result['curve'], window['test']) for name,result in results.items()}
    returns = {}
    for name,result in results.items():
        nav = np.r_[plan['budget_usd'], [r['equity'] for r in result['curve']]]
        returns[name] = nav[1:]/nav[:-1]-1
    code_files = ['quantcore/research/walk_forward.py','quantcore/backtesting/portfolio.py',
                  'quantcore/strategies/base.py','quantcore/strategies/orders.py','quantcore/risk/limits.py']
    metadata = {'executed_at':datetime.now(timezone.utc).isoformat(), 'source':'Alpaca IEX frozen actual minutes',
        'snapshot_id':snapshot.name, 'snapshot_hashes':manifest['hashes'], 'raw_pages_verified':len(manifest['raw_pages']),
        'regular_minute_rows':len(minutes), 'plan':plan, 'plan_sha256':hashlib.sha256(raw_plan).hexdigest(),
        'code_sha256':hashlib.sha256(b''.join((root/f).read_bytes() for f in code_files)).hexdigest(),
        'oos_period':[oos_days[0],oos_days[-1]], 'oos_sessions':len(oos_days),
        'classification_basis':'UNCLASSIFIED: current SEC metadata collected after this historical evaluation',
        'training_basis':'fixed rule candidates have no fitted weights; expanding training history and subsequent validation select lookback/strategy',
        'portfolio_basis':'one continuous OOS $100000 cash ledger; no reset or stitched independent return curves across folds',
        'limitations':['retrospective archive already observed in older reports; final reserve is not a genuinely unseen external holdout',
            'small selected five-instrument universe and one venue; historical revisions not archived as originally observed',
            'only two walk-forward test windows plus one reserved final window; no proof of stable profitability',
            'prior validation picks cannot inspect future test returns; ties follow the fixed candidate list',
            'classification/cost/thresholds were not optimized; modeled limit fills and no paper dividend credit',
            'paper remains fixed Momentum60; research selection is not automatically deployed']}
    report = {'metadata':metadata, 'decisions':decisions,
        'results':{name:{k:v for k,v in result.items() if k in ['metrics','curve','config','audit']} for name,result in results.items()},
        'paired_uncertainty':paired_bootstrap(returns['selected_oos'], returns['fixed_momentum_60'], plan['seed']),
        'candidate_development_metrics':{name:r['metrics'] for name,r in candidates.items()}}
    (directory/'detail.json').write_text(json.dumps({'report':report,'candidate_results':candidates,'oos_results':results},indent=2,allow_nan=False)+'\n')
    (root/'docs/walk_forward_results.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report
