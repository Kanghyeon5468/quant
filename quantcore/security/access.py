import secrets
import time
from collections import defaultdict, deque


class AccessControl:
    def __init__(self, token='', limit=180):
        self.token, self.limit = token, limit
        self.windows = defaultdict(deque)
        self.tickets = {}

    def authorized(self, authorization):
        return not self.token or secrets.compare_digest(authorization or '', 'Bearer '+self.token)

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
