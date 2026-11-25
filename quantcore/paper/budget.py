"""Explicit, audited budget migration. Never delete intent/fill history."""
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from quantcore.paper.client import PaperError
from quantcore.paper.market import atomic_json
from quantcore.paper.policy import MAX_BUDGET
from quantcore.paper.runner import TERMINAL, Journal, make_plan, number, run_once


def change_budget(client, directory, snapshot, new_budget, *, execute=False, resume_after=False):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    new_budget = number(new_budget)
    if not 0 < new_budget <= MAX_BUDGET or (execute and not resume_after):
        raise PaperError('budget must be in (0, $100,000]; execution requires explicit resume')
    (directory/'STOP').touch()
    automation = directory/'automation'
    mutex = Journal(automation)
    try:
        with mutex.lock():
            journal = Journal(directory)
            try:
                with journal.lock():
                    journal.reconcile(client)
                    context = client.context()
                    config = journal.configuration()
                    if not config:
                        raise PaperError('initialize the paper journal before changing its budget')
                    # Validates account identity, own fills, unrelated orders, calendar and input freshness.
                    make_plan(snapshot, context, journal, config['strategy'], journal.budget())
                    old_budget = journal.budget()
                    history = directory/'budget_changes'
                    history.mkdir(parents=True, exist_ok=True)
                    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
                    backup = sqlite3.connect(history/(stamp+'.sqlite3'))
                    try:
                        journal.db.backup(backup)
                    finally:
                        backup.close()
                    if new_budget != old_budget:
                        for row in journal.records():
                            if row['state'] not in TERMINAL | {'rejected_locally'}:
                                client.request('DELETE', '/v2/orders/'+row['response']['id'])
                        for attempt in range(4):
                            journal.reconcile(client)
                            if all(r['state'] in TERMINAL | {'rejected_locally'} for r in journal.records()):
                                break
                            if attempt < 3:
                                time.sleep(1)
                        else:
                            raise PaperError('paper cancellation not final; budget unchanged and automation stays paused')
                        # Cancellations can race with fills: re-read positions and use actual filled_qty.
                        context = client.context()
                        make_plan(snapshot, context, journal, config['strategy'], old_budget)
                        config = journal.change_budget(new_budget, 'Explicit cash-only change within the user-authorized $100,000 ceiling')
                    report = {'mode': 'paper', 'checked_at': datetime.now(timezone.utc).isoformat(),
                              'old_budget_usd': str(old_budget), 'budget_usd': str(new_budget),
                              'budget_revision': config.get('budget_revision', 0), 'history_retained': True}
            finally:
                journal.close()
            if resume_after:
                (directory/'STOP').unlink(missing_ok=True)
            try:
                result = run_once(client, directory, snapshot, config['strategy'], submit=execute)
            except Exception:
                (directory/'STOP').touch()
                raise
            report.update(submitted=execute, orders=result['orders'], journal=result['journal'])
            state_path = automation/'state.json'
            state = json.loads(state_path.read_text()) if state_path.exists() else {'completed_sessions': []}
            state.update(budget_usd=str(new_budget), budget_revision=report['budget_revision'],
                         phase='budget_reconfigured', last_budget_change_at=report['checked_at'])
            if resume_after:
                state.update(blocked=False, consecutive_failures=0)
                state.pop('retry_after', None)
                state.pop('error', None)
            if execute:
                key = result['execution_session']+(f':r{report["budget_revision"]}' if report['budget_revision'] else '')
                state['completed_sessions'] = (state['completed_sessions']+[key])[-30:]
                state['last_evaluation'] = {k: result[k] for k in ('signal_session', 'execution_session',
                    'budget_usd', 'budget_revision', 'snapshot_id', 'snapshot_hashes')}
                state['last_evaluation']['new_orders'] = len(result['orders'])
            atomic_json(state_path, state)
            atomic_json(history/(stamp+'.json'), report)
            atomic_json(directory/'latest_budget_change.json', report)
            return report
    finally:
        mutex.close()
