import hashlib
import json
import secrets
import time
from collections import defaultdict, deque


class AccessControl:
    def __init__(self, token='', limit=180, users_json=''):
        self.token, self.limit = token, limit
        self.users = json.loads(users_json) if users_json else {}
        if not isinstance(self.users, dict) or (users_json and not self.users):
            raise ValueError('configure at least one API user')
        for digest, role in self.users.items():
            if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest) or role not in ('viewer', 'researcher'):
                raise ValueError('API users require SHA-256 hex digests and viewer/researcher roles')
        self.windows = defaultdict(deque)
        self.tickets = {}

    def role(self, authorization):
        if self.users:
            scheme, _, key = (authorization or '').partition(' ')
            if scheme != 'Bearer' or not key:
                return None
            digest = hashlib.sha256(key.encode()).hexdigest()
            return next((role for expected, role in self.users.items() if secrets.compare_digest(digest, expected)), None)
        if not self.token or secrets.compare_digest(authorization or '', 'Bearer '+self.token):
            return 'researcher'
        return None

    def authorized(self, authorization):
        return self.role(authorization) is not None

    def allow(self, client):
        now = time.monotonic()
        window = self.windows[client]
        while window and window[0] < now-60:
            window.popleft()
        if len(window) >= self.limit:
            return False
        window.append(now)
        return True

    def ticket(self):
        now = time.monotonic()
        self.tickets = {k: expiry for k, expiry in self.tickets.items() if expiry > now}
        value = secrets.token_urlsafe(32)
        self.tickets[value] = now+30
        return value

    def consume(self, ticket):
        return self.tickets.pop(ticket, 0) > time.monotonic()
