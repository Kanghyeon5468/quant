"""Market-data GET only. Credentials stay in memory; snapshots contain no headers."""
import gzip
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
from dotenv import dotenv_values

from quantcore.backtesting.engine import CorporateAction
from quantcore.core.models import Bar
from quantcore.data.calendar import action_open, sessions

SYMBOLS = ('AAPL', 'MSFT', 'NVDA', 'TSLA', 'SPY')


class AlpacaData:
    def __init__(self, env_file=None, transport=None):
        import os
        values = dotenv_values(env_file) if env_file else os.environ
        key = values.get('ALPACA_API_KEY') or values.get('APCA_API_KEY_ID')
        secret = values.get('ALPACA_SECRET_KEY') or values.get('APCA_API_SECRET_KEY')
        if not key or not secret:
            raise ValueError('Alpaca market-data credentials missing; set environment or --env-file')
        self.client = httpx.Client(base_url='https://data.alpaca.markets', timeout=60, transport=transport,
            headers={'APCA-API-KEY-ID': key, 'APCA-API-SECRET-KEY': secret})
        self.next_request = 0.

    def pages(self, path, params):
        if path not in ('/v2/stocks/bars', '/v1/corporate-actions', '/v1beta1/news'):
            raise ValueError('only authorized market-data endpoints are allowed')
        seen = set()
        for _ in range(500):
            time.sleep(max(0, self.next_request-time.monotonic()))
            for attempt in range(3):
                try:
                    response = self.client.get(path, params=params)
                except (httpx.TimeoutException, httpx.NetworkError):
                    if attempt == 2:
                        raise RuntimeError('market-data network request failed') from None
                    time.sleep(2**attempt)
                    continue
                if response.status_code in (401, 403, 429):
                    raise RuntimeError(f'market-data request stopped: HTTP {response.status_code}; no entitlement bypass')
                if response.status_code >= 500 and attempt < 2:
                    time.sleep(2**attempt)
                    continue
                if response.status_code != 200:
                    raise RuntimeError(f'market-data request failed: HTTP {response.status_code}')
                break
            self.next_request = time.monotonic()+.6
            data = response.json()
            yield data
            token = data.get('next_page_token')
            if not token:
                return
            if token in seen:
                raise ValueError('pagination token cycle')
            seen.add(token)
            params = {**params, 'page_token': token}
        raise RuntimeError('market-data page limit exceeded')

    def close(self):
        self.client.close()


def corporate_actions(payload, start, end):
    result = {symbol: [] for symbol in SYMBOLS}
    unsupported = {kind for kind, rows in payload.items() if rows and kind not in ('forward_splits', 'reverse_splits', 'cash_dividends')}
    if unsupported:
        raise ValueError('unsupported corporate actions: '+','.join(sorted(unsupported)))
    seen = set()
    for kind, rows in payload.items():
        for row in rows:
            symbol = row['symbol']
            if symbol not in result or not start <= row['ex_date'] <= end or row['id'] in seen:
                continue
            seen.add(row['id'])
            at = action_open(row['ex_date'])
            if at.tz_convert('America/New_York').date().isoformat() != row['ex_date']:
                raise ValueError('corporate action ex-date is not an exchange session')
            if kind in ('forward_splits', 'reverse_splits'):
                value = float(row['new_rate'])/float(row['old_rate'])
                if not np.isfinite(value) or value <= 0:
                    raise ValueError('invalid split ratio')
                result[symbol].append(CorporateAction(at, 'split', value, action_id=row['id']))
            elif kind == 'cash_dividends':
                if row.get('foreign') or row.get('currency', 'USD') not in ('', 'USD') or not row.get('payable_date'):
                    raise ValueError('dividend currency/payment date not established')
                # Conservative cash access: first exchange session AFTER payable date.
                payment = action_open(row['payable_date'], strict_after=True)
                result[symbol].append(CorporateAction(at, 'dividend', float(row['rate']), payment, row['id']))
    return {symbol: sorted(items, key=lambda a: (a.effective_at, a.kind != 'split')) for symbol, items in result.items()}


def regular_daily(minutes, schedule, actions, symbols=SYMBOLS):
    data = minutes.copy()
    data['bar_at'] = pd.to_datetime(data['t'], utc=True)
    if data.duplicated(['symbol', 'bar_at']).any():
        raise ValueError('duplicate minute bars')
    data['session'] = data.bar_at.dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d')
    data = data.merge(schedule.rename(columns={'open': 'session_open', 'close': 'session_close'}),
                      left_on='session', right_index=True, how='inner')
    data = data[(data.bar_at >= data.session_open) & (data.bar_at+pd.Timedelta(minutes=1) <= data.session_close)]
    rows = []
    for (symbol, session), group in data.groupby(['symbol', 'session'], sort=True):
        group = group.sort_values('bar_at')
        clock = schedule.loc[session]
        first, last = group.iloc[0], group.iloc[-1]
        if first.bar_at-clock['open'] > pd.Timedelta(minutes=5) or clock['close']-last.bar_at-pd.Timedelta(minutes=1) > pd.Timedelta(minutes=5):
            raise ValueError(f'{symbol} {session}: opening/closing quote older than five minutes')
        record = Bar(symbol=symbol, timestamp=clock['close'], available_at=clock['close']+pd.Timedelta(minutes=1),
            open=float(first.o), high=float(group.h.max()), low=float(group.l.min()), close=float(last.c),
            volume=int(group.v.sum()), currency='USD', source='alpaca-iex-regular-1min', mode='historical')
        rows.append({**record.model_dump(), 'session': session, 'execution_open': first.bar_at,
            'session_open': clock['open'], 'last_minute_at': last.bar_at, 'minute_bars': len(group),
            'first_minute_volume': int(first.v), 'open_delay_seconds': (first.bar_at-clock['open']).total_seconds(),
            'close_age_seconds': (clock['close']-last.bar_at-pd.Timedelta(minutes=1)).total_seconds()})
    if not rows:
        raise ValueError('no regular-session observations')
    frame = pd.DataFrame(rows).sort_values(['symbol', 'timestamp'])
    for symbol in symbols:
        group = frame[frame.symbol == symbol]
        if set(group.session) != set(schedule.index):
            raise ValueError(f'{symbol}: missing exchange sessions; do not fill prices')
        factor = np.ones(len(group))
        for action in actions[symbol]:
            if action.kind == 'split':
                factor[group.timestamp.to_numpy() >= action.effective_at] *= action.value
        frame.loc[group.index, 'signal_close'] = group.close.to_numpy()*factor
    return frame.reset_index(drop=True), len(data)


def collect_snapshot(directory, env_file, start='2025-07-01', as_of=None):
    now = pd.Timestamp(as_of or datetime.now(timezone.utc))
    if now.tzinfo is None:
        raise ValueError('as_of must have a timezone')
    schedule = sessions(start, now.tz_convert('America/New_York').date(), now)
    if len(schedule) < 313:
        raise ValueError('at least 252 evaluation plus 60 warmup sessions required')
    end = schedule.index[-1]
    target = Path(directory)/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    target.mkdir(parents=True, exist_ok=False)
    client = AlpacaData(env_file)
    frames, raw_files, payload = [], [], {}
    try:
        params = {'symbols': ','.join(SYMBOLS), 'start': start+'T00:00:00Z',
            'end': (pd.Timestamp(end)+pd.Timedelta(days=1)).strftime('%Y-%m-%dT00:00:00Z'),
            'timeframe': '1Min', 'adjustment': 'raw', 'feed': 'iex', 'limit': 10000, 'sort': 'asc'}
        for i, page in enumerate(client.pages('/v2/stocks/bars', params)):
            if not isinstance(page.get('bars'), dict):
                raise ValueError('bars payload missing')
            raw = json.dumps(page, sort_keys=True).encode()
            name = f'raw_bars_{i:03d}.json.gz'
            with gzip.open(target/name, 'wb') as handle:
                handle.write(raw)
            raw_files.append({'name': name, 'sha256_uncompressed': hashlib.sha256(raw).hexdigest()})
            for symbol, rows in page['bars'].items():
                if rows:
                    frames.append(pd.DataFrame(rows).assign(symbol=symbol))
            if i % 10 == 0:
                print(f'Alpaca minute-data pages: {i+1}', flush=True)
        action_params = {'symbols': ','.join(SYMBOLS), 'start': start,
            'end': (pd.Timestamp(end)+pd.Timedelta(days=60)).date().isoformat(), 'limit': 1000}
        for i, page in enumerate(client.pages('/v1/corporate-actions', action_params)):
            for kind, rows in page.get('corporate_actions', {}).items():
                payload.setdefault(kind, []).extend(rows)
        actions = corporate_actions(payload, start, end)
        minutes = pd.concat(frames, ignore_index=True)
        daily, regular_count = regular_daily(minutes, schedule, actions)
        daily.to_parquet(target/'prices.parquet', index=False)
        schedule.to_csv(target/'calendar.csv')
        (target/'actions.json').write_text(json.dumps(payload, indent=2)+'\n')
        hashes = {name: hashlib.sha256((target/name).read_bytes()).hexdigest()
                  for name in ('prices.parquet', 'actions.json', 'calendar.csv')}
        manifest = {'status': 'complete', 'source': 'alpaca-iex-regular-1min', 'data_mode': 'historical',
            'collected_at': datetime.now(timezone.utc).isoformat(), 'as_of': now.isoformat(), 'start': schedule.index[0], 'end': end,
            'symbols': list(SYMBOLS), 'sessions': len(schedule), 'minute_rows_downloaded': len(minutes),
            'regular_minute_rows': regular_count, 'daily_rows': len(daily), 'hashes': hashes, 'raw_pages': raw_files,
            'feed': 'iex', 'adjustment': 'raw', 'calendar': 'XNYS', 'bar_availability_delay_minutes_assumed': 1,
            'rights': 'private personal research; no raw data redistribution', 'actions_counts': {k: len(v) for k,v in payload.items()},
            'opening_delay_max_seconds': float(daily.open_delay_seconds.max()), 'closing_age_max_seconds': float(daily.close_age_seconds.max())}
        (target/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
        Path(directory).mkdir(exist_ok=True)
        (Path(directory)/'latest.json').write_text(json.dumps({'snapshot_directory': str(target.resolve())}, indent=2)+'\n')
        return target
    except Exception as error:
        (target/'failure.json').write_text(json.dumps({'status': 'failed', 'error_type': type(error).__name__, 'message': str(error)})+'\n')
        raise
    finally:
        client.close()


def load_snapshot(directory):
    directory = Path(directory)
    manifest = json.loads((directory/'manifest.json').read_text())
    if manifest.get('status') != 'complete' or manifest.get('data_mode') != 'historical':
        raise ValueError('not a complete actual-data snapshot')
    for name, expected in manifest['hashes'].items():
        if hashlib.sha256((directory/name).read_bytes()).hexdigest() != expected:
            raise ValueError('snapshot hash mismatch: '+name)
    prices = pd.read_parquet(directory/'prices.parquet')
    actions = corporate_actions(json.loads((directory/'actions.json').read_text()), manifest['start'], manifest['end'])
    return prices, actions, manifest
