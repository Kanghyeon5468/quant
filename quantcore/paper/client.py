"""Narrow Alpaca paper API client. No configurable trading host or live mode."""
import os
import re
from decimal import Decimal

import httpx
from dotenv import dotenv_values

from quantcore.data.providers.alpaca import SYMBOLS
from quantcore.paper.policy import MAX_SYMBOL_BUY

PAPER_URL = 'https://paper-api.alpaca.markets'
ORDER_FIELDS = {'symbol', 'qty', 'side', 'type', 'time_in_force', 'limit_price',
                'extended_hours', 'client_order_id'}


class PaperError(RuntimeError):
    def __init__(self, message, *, retryable=False):
        super().__init__(message)
        self.retryable = retryable


class AmbiguousOrder(PaperError):
    """A POST may have reached the broker. Reconcile; never retry it blindly."""


def validate_order(order):
    if set(order) != ORDER_FIELDS or order['symbol'] not in SYMBOLS:
        raise ValueError('only the configured US equity limit-order fields are allowed')
    if order['side'] not in ('buy', 'sell') or order['type'] != 'limit':
        raise ValueError('only long-position buy/sell limit orders are allowed')
    if order['time_in_force'] != 'day' or order['extended_hours'] is not False:
        raise ValueError('paper orders are DAY, regular session only')
    qty, price = Decimal(str(order['qty'])), Decimal(str(order['limit_price']))
    if not qty.is_finite() or qty <= 0 or qty != qty.to_integral_value():
        raise ValueError('quantity must be a positive whole number')
    if not price.is_finite() or price <= 0 or price != price.quantize(Decimal('.01')):
        raise ValueError('limit price must be positive USD cents')
    if not re.fullmatch(r'qcp1-[a-zA-Z0-9-]{1,100}', order['client_order_id']):
        raise ValueError('client order ID must belong to this paper strategy')
    if order['side'] == 'buy' and qty*price > MAX_SYMBOL_BUY:
        raise ValueError('paper buy exceeds the $20,000 per-symbol ceiling')


class PaperClient:
    def __init__(self, env_file=None, transport=None):
        values = dotenv_values(env_file) if env_file else os.environ
        for name in ('APCA_API_BASE_URL', 'ALPACA_BASE_URL', 'ALPACA_API_URL'):
            if values.get(name) and values[name].rstrip('/') != PAPER_URL:
                raise PaperError('configured trading endpoint is not the paper server')
        key = values.get('ALPACA_PAPER_API_KEY') or values.get('ALPACA_API_KEY') or values.get('APCA_API_KEY_ID')
        secret = values.get('ALPACA_PAPER_SECRET_KEY') or values.get('ALPACA_SECRET_KEY') or values.get('APCA_API_SECRET_KEY')
        if not key or not secret:
            raise PaperError('Alpaca paper credentials missing')
        self.client = httpx.Client(base_url=PAPER_URL, transport=transport, timeout=25,
            follow_redirects=False, headers={'APCA-API-KEY-ID': key, 'APCA-API-SECRET-KEY': secret})

    def request(self, method, path, *, params=None, order=None, missing_ok=False):
        if str(self.client.base_url).rstrip('/') != PAPER_URL:
            raise PaperError('paper host guard failed')
        allowed_get = path in ('/v2/account', '/v2/clock', '/v2/positions', '/v2/orders',
                                '/v2/orders:by_client_order_id', '/v2/account/portfolio/history', '/v2/account/activities')
        allowed_get |= path.startswith('/v2/assets/') and path.removeprefix('/v2/assets/') in SYMBOLS
        if method == 'GET' and allowed_get:
            pass
        elif method == 'POST' and path == '/v2/orders':
            validate_order(order)
        elif method == 'DELETE' and re.fullmatch(r'/v2/orders/[0-9a-fA-F-]{36}', path):
            pass
        else:
            raise PaperError('paper API method/path not allowed')
        try:
            response = self.client.request(method, path, params=params, json=order)
        except httpx.TransportError:
            if method == 'POST':
                raise AmbiguousOrder('paper order outcome unknown; reconcile by client_order_id') from None
            raise PaperError('paper API network request failed', retryable=True) from None
        if missing_ok and method == 'GET' and response.status_code == 404:
            return None
        if method == 'POST' and response.status_code >= 500:
            raise AmbiguousOrder('paper server error; order outcome must be reconciled')
        if response.status_code not in (200, 201, 204):
            raise PaperError(f'paper API {method} {path.split("/")[-1]}: HTTP {response.status_code}',
                             retryable=method == 'GET' and (response.status_code == 429 or response.status_code >= 500))
        if response.status_code == 204:
            return None
        try:
            return response.json()
        except ValueError:
            if method == 'POST':
                raise AmbiguousOrder('unreadable paper order response; reconcile before retry') from None
            raise PaperError('invalid paper API JSON') from None

    def portfolio_history(self, start, end):
        return self.request('GET', '/v2/account/portfolio/history', params={
            'start': start, 'end': end, 'timeframe': '1D', 'cashflow_types': 'ALL'})

    def activities(self, after, until):
        params = {'after': after, 'until': until, 'direction': 'asc', 'page_size': 100}
        rows, seen, tokens = [], set(), set()
        for _ in range(100):
            page = self.request('GET', '/v2/account/activities', params=params)
            if not isinstance(page, list) or any(not isinstance(r, dict) or not r.get('id') for r in page):
                raise PaperError('invalid account activities page')
            for row in page:
                if row['id'] not in seen:
                    rows.append(row)
                    seen.add(row['id'])
            if len(page) < 100:
                return rows
            token = page[-1]['id']
            if token in tokens:
                raise PaperError('account activities pagination cycle')
            tokens.add(token)
            params['page_token'] = token
        raise PaperError('account activities page limit exceeded; incomplete history')

    def by_client_id(self, client_id):
        return self.request('GET', '/v2/orders:by_client_order_id',
                            params={'client_order_id': client_id}, missing_ok=True)

    def context(self):
        account = self.request('GET', '/v2/account')
        if (account.get('status') != 'ACTIVE' or account.get('currency') != 'USD'
                or any(account.get(k) for k in ('trading_blocked', 'account_blocked', 'trade_suspended_by_user'))):
            raise PaperError('paper account is not active USD or trading is blocked')
        orders = self.request('GET', '/v2/orders', params={'status': 'open', 'limit': 500, 'nested': 'false'})
        if len(orders) >= 500:
            raise PaperError('open-order list may be truncated; stop')
        return {'account': account, 'clock': self.request('GET', '/v2/clock'),
                'positions': self.request('GET', '/v2/positions'), 'open_orders': orders}

    def close(self):
        self.client.close()
