"""Read-only public projections. Never reads the broker journal or credentials."""
import json
from datetime import datetime, timezone
from pathlib import Path


def read_report(directory, name):
    filename = {'portfolio': 'portfolio_backtest_results.json', 'validation': 'walk_forward_results.json', 'risk': 'status.json'}[name]
    path = Path(directory)/filename
    if not path.is_file():
        return {'status': 'unavailable', 'reason': f'{name} report is not available on this server'}
    try:
        report = json.loads(path.read_text())
        if name in ('portfolio','validation'):
            return {k: report[k] for k in ('metadata', 'results', 'decisions', 'paired_uncertainty') if k in report}
        keys = ('checked_at', 'status', 'data_status', 'reason', 'strategy_nav', 'daily_return', 'drawdown',
                'daily_start', 'peak', 'budget_usd', 'current', 'projected', 'limits', 'risk_policy_version',
                'features_as_of', 'alerts', 'daily_latched', 'drawdown_latched', 'halt_rules',
                'current_violations', 'classification', 'sector_unclassified', 'sector_basis', 'pending_cancellations')
        public = redact_private({k: report[k] for k in keys if k in report})
        at = datetime.fromisoformat(public['checked_at'])
        age = (datetime.now(timezone.utc)-at).total_seconds()
        public.update(age_seconds=age, stale=age > 600 or age < -60, mode='paper')
        return public
    except (OSError, ValueError, KeyError, TypeError):
        return {'status': 'unavailable', 'reason': 'invalid report; no successful risk status assumed'}


def read_performance(directory):
    path = Path(directory)/'status.json'
    if not path.is_file():
        return {'status': 'unavailable', 'reason': 'paper 실적 수집본이 아직 없습니다.'}
    try:
        value = json.loads(path.read_text())
        keys = ('mode', 'currency', 'status', 'checked_at', 'broker_observed_at', 'source', 'tracking_started_at', 'history_checked_at',
                'activities_checked_at', 'history_base_value', 'history_base_value_asof', 'unfunded_points_excluded',
                'collection_errors', 'sections', 'account', 'pnl', 'execution', 'current_revision_execution',
                'orders', 'approved_manual_closures', 'positions', 'corporate_actions', 'daily_history', 'observations', 'comparison', 'latest_decisions', 'notes')
        public = redact_private({k: value[k] for k in keys if k in value})
        age = (datetime.now(timezone.utc)-datetime.fromisoformat(public['checked_at'])).total_seconds()
        public.update(age_seconds=age, stale=age > 600 or age < -60)
        error_file = Path(directory)/'error.json'
        if error_file.exists():
            error = json.loads(error_file.read_text())
            if datetime.fromisoformat(error['checked_at']) > datetime.fromisoformat(public['checked_at']):
                public.update(status='degraded', collection_failed=True, stale=True,
                              failed_at=error['checked_at'])
        return public
    except (ValueError, TypeError, KeyError):
        return {'status': 'unavailable', 'reason': 'paper 실적 보고서 형식이 올바르지 않습니다.'}


def redact_private(value):
    blocked = {'id', 'account_id', 'account_hash', 'asset_id', 'order_id', 'client_id', 'client_order_id',
               'api_key', 'apikey', 'secret_key', 'secret', 'authorization', 'headers', 'response', 'payload'}
    if isinstance(value, dict):
        return {k: redact_private(v) for k,v in value.items() if k.lower() not in blocked}
    if isinstance(value, list):
        return [redact_private(v) for v in value]
    return value


def read_corporate(directory):
    path = Path(directory)/'status.json'
    if not path.exists():
        return {'status':'unavailable','reason':'기업 분류·기업행사 수집본이 없습니다.'}
    try:
        report = redact_private(json.loads(path.read_text()))
        age = (datetime.now(timezone.utc)-datetime.fromisoformat(report['checked_at'])).total_seconds()
        return {**report,'stale':age>600 or age < -60,'age_seconds':age}
    except (ValueError,TypeError,KeyError):
        return {'status':'unavailable','reason':'기업행사 보고서를 읽을 수 없습니다.'}
