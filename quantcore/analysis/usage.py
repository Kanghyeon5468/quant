"""Publish quota and token counters without exposing the private request ledger."""

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from quantcore.core.files import atomic_json

USAGE_KEYS = ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens', 'output_tokens')


def claude_limits(headers, observed_at):
    limits = {}
    for kind in ('input', 'output', 'tokens'):
        prefix = 'anthropic-ratelimit-' + (kind + '-tokens' if kind != 'tokens' else kind)
        try:
            remaining = int(headers[prefix + '-remaining'])
            reset = datetime.fromisoformat(headers[prefix + '-reset'])
        except (KeyError, ValueError):
            continue
        if remaining >= 0 and reset.tzinfo is not None:
            limits[kind] = {'remaining': remaining, 'reset_at': reset.astimezone(timezone.utc).isoformat()}
    return {'observed_at': observed_at, 'limits': limits} if limits else None


def claude_tokens(usage):
    counts = [usage.get(k, 0) for k in USAGE_KEYS] if isinstance(usage, dict) else []
    if (counts and 'input_tokens' in usage and 'output_tokens' in usage
            and all(type(n) is int and n >= 0 for n in counts)):
        return {'input': sum(counts[:-1]), 'output': counts[-1]}
    return None


def publish_usage(root, ready, daily_limit, *, at=None):
    root = Path(root)
    at = at or datetime.now(timezone.utc)
    day = at.replace(hour=0, minute=0, second=0, microsecond=0)
    ledger = root / 'artifacts/llm/requests.sqlite3'
    if not ledger.is_file():
        return
    with closing(sqlite3.connect(ledger.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        rows = db.execute('SELECT started_at,status,result FROM requests WHERE started_at<=? ORDER BY started_at DESC',
                          (at.isoformat(),)).fetchall()

    daily = {'date_utc': day.date().isoformat(), 'reset_at': (day + timedelta(days=1)).isoformat(),
             'limit': daily_limit, 'started': 0, 'failed': 0, 'pending': 0}
    totals = {'input': 0, 'output': 0, 'requests_with_usage': 0}
    today = totals.copy()
    latest_usage = latest_limit = None
    for started_at, status, raw in rows:
        is_today = started_at >= day.isoformat()
        if is_today:
            daily['started'] += 1
            if status in ('failed', 'pending'):
                daily[status] += 1
        result = json.loads(raw) if raw else {}
        if result.get('provider') != 'anthropic':
            continue
        tokens = claude_tokens(result.get('usage'))
        if tokens is not None:
            latest_usage = latest_usage or {'model': result.get('model'),
                                           'at': result.get('analyzed_at', started_at), **tokens}
            for summary in (totals, today) if is_today else (totals,):
                summary['input'] += tokens['input']
                summary['output'] += tokens['output']
                summary['requests_with_usage'] += 1
        if latest_limit is None and result.get('model') == ready.get('model') and ready.get('provider') == 'anthropic':
            latest_limit = result.get('token_rate_limit')

    daily['remaining'] = max(daily_limit - daily['started'], 0)
    atomic_json(root / 'datasets/information/llm_usage.json', {
        'status': 'ok', 'checked_at': at.isoformat(),
        'configuration': {k: ready.get(k) for k in ('status', 'provider', 'model')},
        'daily_requests': daily, 'today_tokens': today, 'recorded_tokens': totals,
        'latest_usage': latest_usage, 'anthropic_rate_limit': latest_limit,
    })


def read_usage(data_directory, *, at=None):
    at = at or datetime.now(timezone.utc)
    path = Path(data_directory) / 'information/llm_usage.json'
    try:
        report = json.loads(path.read_text())
        age = (at - datetime.fromisoformat(report['checked_at'])).total_seconds()
        report['stale'] = age > 1800 or age < -60 or report['daily_requests']['date_utc'] != at.date().isoformat()
        return report
    except (OSError, ValueError, TypeError, KeyError):
        return {'status': 'unavailable'}
