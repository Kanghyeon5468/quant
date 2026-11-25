"""Persistent paper intents and identity checks shared by execution and corporate accounting."""
import fcntl
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from quantcore.data.providers.alpaca import SYMBOLS
from quantcore.paper.client import AmbiguousOrder, PaperError
from quantcore.paper.policy import INITIAL_BUDGET, MAX_BUDGET
from quantcore.strategies.orders import OrderPolicy, limit_price, modeled_cost

TERMINAL = {'filled', 'canceled', 'expired', 'rejected', 'replaced'}


def number(value):
    result = Decimal(str(value))
    if not result.is_finite():
        raise PaperError('non-finite account/position value')
    return result


class Journal:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.directory/'journal.sqlite3')
        self.db.execute('CREATE TABLE IF NOT EXISTS config (id INTEGER PRIMARY KEY, value TEXT NOT NULL)')
        self.db.execute('''CREATE TABLE IF NOT EXISTS orders (
            client_id TEXT PRIMARY KEY, payload TEXT NOT NULL, state TEXT NOT NULL,
            response TEXT, updated_at TEXT NOT NULL)''')
        self.db.commit()

    @contextmanager
    def lock(self):
        with (self.directory/'runner.lock').open('a') as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise PaperError('another paper runner holds this journal') from None
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def configure(self, account_id, strategy, budget):
        config = {'account_hash': hashlib.sha256(account_id.encode()).hexdigest(),
                  'strategy': strategy, 'budget': str(budget), 'universe': list(SYMBOLS)}
        encoded = json.dumps(config, sort_keys=True)
        previous = self.configuration()
        if previous and any(previous.get(k) != v for k, v in config.items()):
            raise PaperError('journal belongs to a different account, strategy or budget')
        if not previous:
            self.db.execute('INSERT INTO config VALUES (1, ?)', (encoded,))
            self.db.commit()
        return config['account_hash'][:8]

    def configuration(self):
        row = self.db.execute('SELECT value FROM config WHERE id=1').fetchone()
        return json.loads(row[0]) if row else None

    def budget(self):
        config = self.configuration()
        return number(config['budget']) if config else INITIAL_BUDGET

    def revision(self):
        return (self.configuration() or {}).get('budget_revision', 0)

    def change_budget(self, budget, reason):
        budget = number(budget)
        if not 0 < budget <= MAX_BUDGET:
            raise PaperError('paper budget must be in (0, $100,000]')
        config = self.configuration()
        if not config:
            raise PaperError('initialize the paper journal before changing its budget')
        if number(config['budget']) == budget:
            return config
        if any(r['state'] not in TERMINAL | {'rejected_locally'} for r in self.records()):
            raise PaperError('confirm all own pending cancellations before changing the budget')
        revision = config.get('budget_revision', 0)+1
        self.db.execute('''CREATE TABLE IF NOT EXISTS budget_changes (
            revision INTEGER PRIMARY KEY, old_budget TEXT, new_budget TEXT, changed_at TEXT, reason TEXT)''')
        self.db.execute('INSERT INTO budget_changes VALUES (?, ?, ?, ?, ?)',
                        (revision, config['budget'], str(budget), datetime.now(timezone.utc).isoformat(), reason))
        config.update(budget=str(budget), budget_revision=revision)
        self.db.execute('UPDATE config SET value=? WHERE id=1', (json.dumps(config, sort_keys=True),))
        self.db.commit()
        return config

    def records(self):
        return [{'client_id': cid, 'payload': json.loads(payload), 'state': state,
                 'response': json.loads(response) if response else None}
                for cid, payload, state, response in self.db.execute(
                    'SELECT client_id, payload, state, response FROM orders ORDER BY client_id')]

    def save(self, payload, state, response=None):
        self.db.execute('''INSERT INTO orders VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(client_id) DO UPDATE SET state=excluded.state,
            response=excluded.response, updated_at=excluded.updated_at''',
            (payload['client_order_id'], json.dumps(payload, sort_keys=True), state,
             json.dumps(response) if response is not None else None, datetime.now(timezone.utc).isoformat()))
        self.db.commit()

    def reconcile(self, client):
        for record in self.records():
            if record['state'] in TERMINAL | {'rejected_locally'}:
                continue  # Final fills remain in the ledger; do not poll all history forever.
            remote = client.by_client_id(record['client_id'])
            if remote:
                check_response(record['payload'], remote)
                self.save(record['payload'], remote['status'], remote)
            elif record['state'] != 'rejected_locally':
                # Includes crash between durable intent and POST; do not guess or resend.
                raise AmbiguousOrder('journal order absent at broker; inspect before creating more orders')

    def close(self):
        self.db.close()

    def record_model(self, plan):
        self.db.execute('CREATE TABLE IF NOT EXISTS order_models (client_id TEXT PRIMARY KEY, data TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS order_evidence (client_id TEXT PRIMARY KEY, data TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS decision_runs (session TEXT PRIMARY KEY, data TEXT)')
        self.db.execute('INSERT OR IGNORE INTO decision_runs VALUES (?, ?)',
            (plan['execution_session']+':r'+str(plan.get('budget_revision', 0)), json.dumps({
                'captured_at': datetime.now(timezone.utc).isoformat(),
                'execution_session': plan['execution_session'], 'signal_session': plan.get('signal_session'),
                'decisions': plan.get('decisions', []), 'rejected': plan.get('risk', {}).get('rejected', [])})))
        candidates = plan['orders']+[r['payload'] for r in self.records() if r['state'] not in TERMINAL]
        policy = OrderPolicy.model_validate(plan['order_policy'])
        for order in candidates:
            ref = plan['references'][order['symbol']]
            if f'-{plan["execution_session"].replace("-", "")}-' not in order['client_order_id']:
                continue
            if number(order['limit_price']) != limit_price(ref['reference_close'], order['side'], policy):
                continue
            evidence = {**plan.get('signal_evidence', {}).get(order['symbol'], {}),
                'captured_at': datetime.now(timezone.utc).isoformat(), 'strategy': plan.get('strategy'),
                'evidence_status': 'captured_before_submission' if order in plan['orders'] else 'reconstructed_after_submission',
                'risk_policy_version': plan.get('risk', {}).get('risk_policy_version'),
                'snapshot_id': plan['snapshot_id'], 'order_policy_version': policy.version}
            self.db.execute('INSERT OR IGNORE INTO order_evidence VALUES (?, ?)',
                (order['client_order_id'], json.dumps(evidence)))
            self.db.execute('INSERT OR IGNORE INTO order_models VALUES (?, ?)',
                (order['client_order_id'], json.dumps({'policy': policy.model_dump(),
                 'policy_version': policy.version, **ref, 'snapshot_id': plan['snapshot_id']})))
        self.db.commit()

    def cost_estimates(self):
        self.db.execute('CREATE TABLE IF NOT EXISTS order_models (client_id TEXT PRIMARY KEY, data TEXT)')
        models = {key: json.loads(raw) for key, raw in self.db.execute('SELECT client_id,data FROM order_models')}
        rows = []
        for r in self.records():
            filled = number((r['response'] or {}).get('filled_qty', 0))
            if not filled:
                continue
            model = models.get(r['client_id'])
            if model and model['average_volume_20']:
                cost = modeled_cost(model['reference_close'], int(r['payload']['qty']),
                                    model['average_volume_20'], OrderPolicy.model_validate(model['policy']))
                fraction = float(filled/number(r['payload']['qty']))
                cost = {k: v*fraction if k != 'adverse_bps' else v for k, v in cost.items()}
                rows.append({'symbol': r['payload']['symbol'], 'filled_qty': str(filled), **cost,
                             'policy_version': model['policy_version'], 'status': 'estimate_only'})
            else:
                rows.append({'symbol': r['payload']['symbol'], 'filled_qty': str(filled), 'status': 'reference_unavailable'})
        return rows


def check_response(payload, response):
    if (response.get('client_order_id') != payload['client_order_id']
            or response.get('symbol') != payload['symbol'] or response.get('side') != payload['side']
            or number(response.get('qty', 'NaN')) != number(payload['qty'])
            or response.get('type') != 'limit' or response.get('time_in_force') != 'day'
            or number(response.get('limit_price', 'NaN')) != number(payload['limit_price'])
            or response.get('extended_hours', False) is not False or not response.get('status')):
        raise AmbiguousOrder('broker response differs from saved paper intent')
    filled = number(response.get('filled_qty', '0'))
    if not 0 <= filled <= number(payload['qty']):
        raise AmbiguousOrder('invalid broker filled quantity')
