import numpy as np
import pandas as pd
import pytest

from quantcore.research.walk_forward import select_candidate, split_windows, window_metrics


def test_chronological_plan_has_disjoint_future_test_windows_and_reserved_last_block():
    days=pd.bdate_range('2025-01-01',periods=264).strftime('%Y-%m-%d').tolist()
    plan={'minimum_training_sessions':96,'validation_sessions':42,'test_sessions':42,'final_holdout_sessions':42}
    windows=split_windows(days,plan)
    assert len(windows)==3
    used=[]
    for window in windows:
        assert window['training'][-1]<window['validation'][0]<window['test'][0]
        assert window['validation'][-1]<window['test'][0]
        used+=window['test']
    assert len(used)==len(set(used))==126 and windows[-1]['kind']=='reserved_holdout'
    assert windows[-1]['test']==days[-42:]


def test_selection_cannot_inspect_future_prices_or_holdout_results():
    days=pd.bdate_range('2026-01-01',periods=160).strftime('%Y-%m-%d').tolist()
    curves={name:[{'session':d,'equity':100000*(1+rate)**i} for i,d in enumerate(days)]
            for name,rate in [('up',.001),('down',-.001)]}
    available={d:pd.Timestamp(d,tz='UTC')+pd.Timedelta(hours=22) for d in days}
    train,valid=days[:96],days[96:138]
    before=select_candidate(curves,train,valid,available,available[valid[-1]])
    for curve in curves.values():
        for row in curve:
            if row['session']>valid[-1]:
                row['equity']*=np.random.default_rng(1).uniform(.1,10)
    assert select_candidate(curves,train,valid,available,available[valid[-1]])==before
    with pytest.raises(ValueError,match='future'):
        select_candidate(curves,train,valid,available,available[valid[-1]]-pd.Timedelta(seconds=1))


def test_window_return_uses_prior_close_as_baseline_and_excludes_later_data():
    curve=[{'session':d,'equity':v} for d,v in [('a',100000),('b',110000),('c',121000),('d',1)]]
    r=window_metrics(curve,['b','c'])
    assert r['total_return']==pytest.approx(.21)
    assert r['max_drawdown']==0 and r['sessions']==2
