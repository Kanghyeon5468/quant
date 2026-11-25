"""A bounded scheduler tick; launchd owns recurrence, never a chat session."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from quantcore.data.calendar import sessions
from quantcore.paper.client import AmbiguousOrder, PaperClient
from quantcore.paper.corporate import reconcile_corporate
from quantcore.paper.market import atomic_json, refresh_snapshot
from quantcore.paper.performance import collect_safely
from quantcore.paper.runner import Journal, monitor_risk, number, run_once, status


def session_task(clock):
    now = pd.Timestamp(clock['timestamp'])
    if now.tzinfo is None:
        raise ValueError('broker clock needs timezone')
    day = now.tz_convert('America/New_York').date()
    complete = sessions(day-pd.Timedelta(days=15), day, now)
    if complete.empty:
        raise ValueError('no completed exchange session')
    if clock['is_open']:
        opened = sessions(day, day).iloc[0]['open']
        if now > opened+pd.Timedelta(minutes=5):
            return None
        execute = str(day)
    else:
        if now < complete.iloc[-1]['close']+pd.Timedelta(minutes=10):
            return None
        execute = str(pd.Timestamp(clock['next_open']).tz_convert('America/New_York').date())
    return {'signal_session': complete.index[-1], 'execution_session': execute}


def tick(root, env_file, strategy='momentum', budget=None):
    root = Path(root)
    directory = root/'artifacts/paper_trading'
    automation = directory/'automation'
    mutex = Journal(automation)
    client = None
    try:
        with mutex.lock():
            state_file = automation/'state.json'
            state = json.loads(state_file.read_text()) if state_file.exists() else {'completed_sessions': []}
            state.update(checked_at=datetime.now(timezone.utc).isoformat(), process_id=os.getpid(),
                         parent_process_id=os.getppid(), mode='paper', poll_interval_seconds=300)
            try:
                client = PaperClient(env_file)
                state['corporate'] = reconcile_corporate(client, root, env_file=env_file)
                observed = status(client, directory)
                revision = observed['budget_revision']
                state.update(budget_usd=observed['budget_usd'], budget_revision=revision)
                state['broker_clock'] = observed['clock']
                state['orders'] = [{'symbol': r['payload']['symbol'], 'side': r['payload']['side'],
                                   'qty': r['payload']['qty'], 'status': r['state'],
                                   'filled_qty': (r['response'] or {}).get('filled_qty', '0')}
                                  for r in observed['journal']]
                state['positions_count'] = len(observed['positions'])
                equity = observed['account_summary'].get('equity')
                if equity is not None:
                    state.setdefault('initial_account_equity', str(number(equity)))
                    state['paper_account_equity'] = str(number(equity))
                    state['paper_account_equity_change'] = str(number(equity)-number(state['initial_account_equity']))
                task = session_task(observed['clock'])
                key = (task['execution_session']+(f':r{revision}' if revision else '')) if task else None
                state['next_task'] = task
                now = pd.Timestamp(observed['clock']['timestamp'])
                if (directory/'STOP').exists():
                    state['phase'] = 'paused'
                elif state.get('blocked'):
                    state['phase'] = 'blocked'
                elif state.get('retry_after') and now < pd.Timestamp(state['retry_after']):
                    state['phase'] = 'retry_wait'
                elif task is None:
                    pointer = root/'datasets/paper_equities/latest.json'
                    if not pointer.exists():
                        pointer = root/'datasets/real_equities/latest.json'
                    snapshot = Path(json.loads(pointer.read_text())['snapshot_directory'])
                    risk = monitor_risk(client, directory, snapshot)
                    state['risk'] = {k: risk.get(k) for k in ('status', 'daily_return', 'drawdown', 'cancel_actions', 'halt_rules')}
                    state['phase'] = 'monitoring'
                elif key in state['completed_sessions']:
                    snapshot = refresh_snapshot(root, env_file, now)
                    risk = monitor_risk(client, directory, snapshot)
                    state['risk'] = {k: risk.get(k) for k in ('status', 'daily_return', 'drawdown', 'cancel_actions', 'halt_rules')}
                    state['phase'] = 'session_already_evaluated'
                else:
                    snapshot = refresh_snapshot(root, env_file, now)
                    result = run_once(client, directory, snapshot, strategy, budget, submit=True)
                    state['risk'] = {k: result['risk'].get(k) for k in ('status', 'daily_return', 'drawdown', 'halt_rules')}
                    state['last_evaluation'] = {'signal_session': result['signal_session'],
                        'execution_session': result['execution_session'], 'new_orders': len(result['orders']),
                        'budget_usd': result['budget_usd'], 'budget_revision': result['budget_revision'],
                        'snapshot_id': result['snapshot_id'], 'snapshot_hashes': result['snapshot_hashes']}
                    state['orders'] = [{'symbol': r['payload']['symbol'], 'side': r['payload']['side'],
                                       'qty': r['payload']['qty'], 'status': r['state'],
                                       'filled_qty': (r['response'] or {}).get('filled_qty', '0')}
                                      for r in result['journal']]
                    state['completed_sessions'] = (state['completed_sessions']+[key])[-30:]
                    state['phase'] = 'evaluated'
                    state['consecutive_failures'] = 0
                    state.pop('retry_after', None)
                    state.pop('error', None)
                if state['phase'] in ('monitoring', 'session_already_evaluated', 'evaluated'):
                    state['consecutive_failures'] = 0
                    state.pop('retry_after', None)
                    state.pop('error', None)
                state['last_success_at'] = datetime.now(timezone.utc).isoformat()
            except Exception as error:
                state['consecutive_failures'] = state.get('consecutive_failures', 0)+1
                message = str(error)
                transient = getattr(error, 'retryable', False) or any(s in message for s in (
                    'network request failed', 'HTTP 429', 'HTTP 500', 'HTTP 502', 'HTTP 503', 'HTTP 504',
                    'minute data unavailable', 'missing exchange sessions', 'another paper runner'))
                transient = transient and not isinstance(error, AmbiguousOrder)
                state['error'] = {'type': type(error).__name__, 'message': message[:240]}
                if transient and state['consecutive_failures'] < 4:
                    state['phase'] = 'retry_wait'
                    state['retry_after'] = (pd.Timestamp.now(tz='UTC')+pd.Timedelta(
                        minutes=5*3**(state['consecutive_failures']-1))).isoformat()
                else:
                    state['blocked'] = True
                    state['phase'] = 'blocked'
            if client is not None:
                state['performance'] = collect_safely(client, root)
            configuration = root/'configs/information.json'
            if configuration.exists() and json.loads(configuration.read_text()).get('enabled'):
                # Research refresh follows the critical order/risk/performance path and cannot clear a halt.
                try:
                    from quantcore.information.collector import refresh
                    state['information'] = refresh(root, env_file)
                except Exception as error:
                    state['information'] = {'status':'failed','reason':str(error)[:180]}
            state['finished_at'] = datetime.now(timezone.utc).isoformat()
            atomic_json(state_file, state)
            # Logs/heartbeat contain no credentials, account/order IDs or raw response bodies.
            return state
    finally:
        if client:
            client.close()
        mutex.close()


def resume(directory):
    automation = Path(directory)/'automation'
    mutex = Journal(automation)
    try:
        with mutex.lock():
            path = automation/'state.json'
            state = json.loads(path.read_text()) if path.exists() else {'completed_sessions': []}
            state.update(blocked=False, consecutive_failures=0)
            state.pop('retry_after', None)
            state.pop('error', None)
            atomic_json(path, state)
            (Path(directory)/'STOP').unlink(missing_ok=True)
    finally:
        mutex.close()
