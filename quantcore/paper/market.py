"""Incremental, private rolling snapshots for automation; research inputs stay frozen."""
import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from quantcore.core.files import atomic_json
from quantcore.data.calendar import sessions
from quantcore.data.providers.alpaca import (
    SYMBOLS,
    AlpacaData,
    corporate_actions,
    load_snapshot,
    regular_daily,
)


def refresh_snapshot(root, env_file, now, *, force=False):
    root, now = Path(root), pd.Timestamp(now)
    if now.tzinfo is None:
        raise ValueError('paper refresh requires a timezone')
    day = now.tz_convert('America/New_York').date()
    schedule = sessions(day-pd.Timedelta(days=180), day, now).iloc[-100:]
    if len(schedule) < 60:
        raise ValueError('insufficient completed sessions')
    start, end = schedule.index[0], schedule.index[-1]
    directory = root/'datasets/paper_equities'
    pointer = directory/'latest.json'
    fallback = root/'datasets/real_equities/latest.json'
    base, prior, source_manifest = None, pd.DataFrame(), None
    if pointer.exists() or fallback.exists():
        base = Path(json.loads((pointer if pointer.exists() else fallback).read_text())['snapshot_directory'])
        prior, _, source_manifest = load_snapshot(base)
        if source_manifest.get('source') != 'alpaca-iex-regular-1min' or source_manifest.get('feed') != 'iex':
            raise ValueError('paper cache is not the actual IEX source')
        if source_manifest['end'] > end:
            raise ValueError('paper cache is from the future')
        if source_manifest['end'] == end and not force:
            return base
        prior = prior[prior.session.isin(schedule.index)].copy()
    known = {s: set(prior[prior.symbol == s].session) if not prior.empty else set() for s in SYMBOLS}
    missing = [d for d in schedule.index if any(d not in known[s] for s in SYMBOLS)]
    update_schedule = schedule.loc[missing[0]:] if missing else schedule.iloc[:0]
    target = directory/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:6])
    target.mkdir(parents=True, exist_ok=False)
    client, downloaded, raw_files, payload = AlpacaData(env_file), [], [], {}
    try:
        if len(update_schedule):
            params = {'symbols': ','.join(SYMBOLS), 'start': update_schedule.index[0]+'T00:00:00Z',
                      'end': (schedule.iloc[-1]['close']+pd.Timedelta(minutes=1)).isoformat(),
                      'timeframe': '1Min', 'adjustment': 'raw', 'feed': 'iex', 'limit': 10000, 'sort': 'asc'}
            for i, page in enumerate(client.pages('/v2/stocks/bars', params)):
                if not isinstance(page.get('bars'), dict):
                    raise ValueError('minute bars payload missing')
                raw = json.dumps(page, sort_keys=True).encode()
                name = f'raw_bars_{i:03d}.json.gz'
                with gzip.open(target/name, 'wb') as handle:
                    handle.write(raw)
                raw_files.append({'name': name, 'sha256_uncompressed': hashlib.sha256(raw).hexdigest()})
                for symbol, rows in page['bars'].items():
                    if rows:
                        downloaded.append(pd.DataFrame(rows).assign(symbol=symbol))
        for page in client.pages('/v1/corporate-actions', {'symbols': ','.join(SYMBOLS), 'start': start,
                                'end': str(pd.Timestamp(end).date()+pd.Timedelta(days=14)), 'limit': 1000}):
            if not isinstance(page.get('corporate_actions'), dict):
                raise ValueError('corporate action payload missing')
            for kind, rows in page['corporate_actions'].items():
                payload.setdefault(kind, []).extend(rows)
        actions = corporate_actions(payload, start, end)
        minute_count = 0
        if len(update_schedule):
            if not downloaded:
                raise ValueError('completed-session minute data unavailable')
            minutes = pd.concat(downloaded, ignore_index=True)
            minute_count = len(minutes)
            update, _ = regular_daily(minutes, update_schedule, actions)
            prior = prior[~prior.session.isin(update_schedule.index)] if not prior.empty else prior
            prior = pd.concat([prior, update], ignore_index=True)
        daily = prior.sort_values(['symbol', 'timestamp']).reset_index(drop=True)
        if daily.duplicated(['symbol', 'session']).any():
            raise ValueError('duplicate paper daily bars')
        for symbol in SYMBOLS:
            group = daily[daily.symbol == symbol]
            if set(group.session) != set(schedule.index):
                raise ValueError('missing paper exchange sessions')
            factor = np.ones(len(group))
            for action in actions[symbol]:
                if action.kind == 'split':
                    factor[group.timestamp.to_numpy() >= action.effective_at] *= action.value
            daily.loc[group.index, 'signal_close'] = group.close.to_numpy()*factor
        daily.to_parquet(target/'prices.parquet', index=False)
        schedule.to_csv(target/'calendar.csv')
        (target/'actions.json').write_text(json.dumps(payload, indent=2)+'\n')
        hashes = {n: hashlib.sha256((target/n).read_bytes()).hexdigest()
                  for n in ('prices.parquet', 'calendar.csv', 'actions.json')}
        manifest = {'status': 'complete', 'data_mode': 'historical', 'source': 'alpaca-iex-regular-1min',
                    'feed': 'iex', 'adjustment': 'raw', 'calendar': 'XNYS', 'start': start, 'end': end,
                    'symbols': list(SYMBOLS), 'sessions': len(schedule), 'daily_rows': len(daily),
                    'collected_at': datetime.now(timezone.utc).isoformat(), 'as_of': now.isoformat(),
                    'hashes': hashes, 'minute_rows_downloaded_this_update': minute_count,
                    'regular_minute_rows': int(daily.minute_bars.sum()), 'raw_pages': raw_files,
                    'base_snapshot': str(base) if base else None,
                    'base_hashes': source_manifest['hashes'] if source_manifest else None,
                    'bar_availability_delay_minutes_assumed': 1, 'rights': 'private personal research; no redistribution'}
        atomic_json(target/'manifest.json', manifest)
        load_snapshot(target)  # Validate the complete frozen result before publishing the pointer.
        atomic_json(pointer, {'snapshot_directory': str(target.resolve())})
        return target
    except Exception as error:
        atomic_json(target/'failure.json', {'status': 'failed', 'error_type': type(error).__name__})
        raise
    finally:
        client.close()
