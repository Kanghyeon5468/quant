"""Versioned current instrument/SIC observations. Today is never backdated into a backtest."""
import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import dotenv_values

from quantcore.core.files import atomic_json
from quantcore.data.providers.alpaca import SYMBOLS, AlpacaData


def utc(value):
    result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('reference timestamp must be timezone-aware')
    return result.astimezone(timezone.utc)


def normalize_actions(payload, collected_at):
    result, seen = [], set()
    for kind, rows in payload.items():
        for row in rows:
            if row['id'] in seen:
                continue
            seen.add(row['id'])
            symbol = row.get('symbol') or row.get('old_symbol') or row.get('acquiree_symbol')
            day = row.get('ex_date') or row.get('effective_date') or row.get('process_date')
            event = {'id': row['id'], 'kind': kind, 'symbol': symbol,
                'effective_date': day, 'effective_time_basis': 'ex_date' if row.get('ex_date') else ('effective_date' if row.get('effective_date') else 'provider process_date'),
                'available_at': collected_at, 'public_at': None, 'source': 'Alpaca corporate actions',
                'source_url': 'https://data.alpaca.markets/v1/corporate-actions', 'raw': row}
            if kind in ('forward_splits', 'reverse_splits'):
                from decimal import Decimal
                old, new = Decimal(str(row['old_rate'])), Decimal(str(row['new_rate']))
                if not old.is_finite() or not new.is_finite() or old <= 0 or new <= 0:
                    raise ValueError('invalid corporate split ratio')
                event.update(type='split', ratio=str(new/old))
            elif kind == 'cash_dividends':
                event.update(type='dividend', rate=str(row['rate']), payable_date=row.get('payable_date'),
                             currency=row.get('currency') or 'USD')
            elif kind == 'name_changes':
                event.update(type='rename', new_symbol=row.get('new_symbol'), old_symbol=row.get('old_symbol'))
            else:
                event['type'] = 'unsupported'
            result.append(event)
    return sorted(result, key=lambda e: (e['effective_date'] or '', e['id']))


def load_reference(root):
    directory = Path(root)/'datasets/reference'
    pointer = directory/'latest.json'
    if not pointer.exists():
        return None
    folder = directory/Path(json.loads(pointer.read_text())['snapshot_directory']).name
    manifest = json.loads((folder/'manifest.json').read_text())
    for name, expected in manifest['hashes'].items():
        if Path(name).name != name or hashlib.sha256((folder/name).read_bytes()).hexdigest() != expected:
            raise ValueError('reference snapshot hash mismatch')
    return {'manifest': manifest, 'securities': json.loads((folder/'securities.json').read_text()),
            'actions': json.loads((folder/'actions.json').read_text()), 'directory': str(folder)}


def classification_asof(root, cutoff):
    """Read immutable observations available at the requested time, including older vintages."""
    directory = Path(root)/'datasets/reference'
    cutoff = utc(cutoff)
    candidates = []
    for path in directory.glob('*/manifest.json'):
        manifest = json.loads(path.read_text())
        observed = utc(manifest['collected_at'])
        if observed <= cutoff and cutoff-observed <= timedelta(days=90):
            candidates.append((observed, path.parent, manifest))
    if not candidates:
        return {}, {'status': 'unavailable', 'reason': 'no classification vintage available at cutoff'}
    _, folder, manifest = max(candidates, key=lambda p: p[0])
    raw = (folder/'securities.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest['hashes']['securities.json']:
        raise ValueError('classification hash mismatch')
    securities = json.loads(raw)
    groups = {s: row['risk_group'] for s, row in securities.items()
              if row.get('status') == 'verified' and row.get('risk_group') and utc(row['available_at']) <= cutoff}
    return groups, {'status': 'available', 'collected_at': manifest['collected_at'],
                    'taxonomy': manifest['taxonomy'], 'securities': securities,
                    'basis': 'SEC SIC-derived project groups; ETF issuer classification; no ETF look-through'}


def collect_reference(root, env_file, paper_client, *, force=False):
    root = Path(root)
    existing = load_reference(root)
    now = datetime.now(timezone.utc)
    if existing and not force and now-utc(existing['manifest']['collected_at']) < timedelta(hours=24):
        return existing
    config = json.loads((root/'configs/security_master.json').read_text())
    user_agent = os.getenv('SEC_USER_AGENT') or dotenv_values(root/'.env').get('SEC_USER_AGENT')
    if not user_agent or '@' not in user_agent:
        if existing:
            return existing
        raise ValueError('set SEC_USER_AGENT with application and real contact email')
    directory = root/'datasets/reference'/now.strftime('%Y%m%dT%H%M%S%fZ')
    directory.mkdir(parents=True)
    assets, securities, hashes = {}, {}, {}
    with httpx.Client(timeout=25, headers={'User-Agent': user_agent}, follow_redirects=False) as sec:
        for symbol in SYMBOLS:
            asset = paper_client.request('GET', '/v2/assets/'+symbol)
            assets[symbol] = asset
            cik = config['companies'][symbol]
            url = f'https://data.sec.gov/submissions/CIK{cik:010d}.json'
            response = sec.get(url)
            if response.status_code != 200:
                raise ValueError(f'SEC metadata stopped: HTTP {response.status_code}; no bypass')
            data = response.json()
            if int(data['cik']) != cik or symbol not in data.get('tickers', []):
                raise ValueError('SEC identity/ticker mapping not verified')
            name = f'sec_{symbol}.json'
            (directory/name).write_bytes(response.content)
            hashes[name] = hashlib.sha256(response.content).hexdigest()
            fund = config.get('funds', {}).get(symbol)
            group = fund['group'] if fund else config['sic_groups'].get(str(data.get('sic')))
            securities[symbol] = {'symbol': symbol, 'name': data['name'], 'cik': cik, 'sic': data.get('sic'),
                'sic_description': data.get('sicDescription'), 'asset_id': asset['id'],
                'asset_class': 'ETF' if fund else 'COMMON_EQUITY', 'exchange': asset.get('exchange'),
                'risk_group': group, 'status': 'verified' if group and asset.get('symbol') == symbol else 'unclassified',
                'available_at': datetime.now(timezone.utc).isoformat(), 'source_url': url,
                'classification_source_url': fund['source_url'] if fund else 'https://www.sec.gov/search-filings/standard-industrial-classification-sic-code-list'}
            time.sleep(.3)
    market = AlpacaData(env_file)
    payload = {}
    try:
        for page in market.pages('/v1/corporate-actions', {'symbols': ','.join(SYMBOLS),
            'start': '2020-01-01', 'end': (now+timedelta(days=60)).date().isoformat(), 'limit': 1000}):
            for kind, rows in page.get('corporate_actions', {}).items():
                payload.setdefault(kind, []).extend(rows)
    finally:
        market.close()
    completed = datetime.now(timezone.utc).isoformat()
    for row in securities.values():
        row['available_at'] = completed
    documents = {'assets.json': assets, 'securities.json': securities,
                 'actions_raw.json': payload, 'actions.json': normalize_actions(payload, completed)}
    for name, value in documents.items():
        raw = json.dumps(value, sort_keys=True, indent=2).encode()
        (directory/name).write_bytes(raw)
        hashes[name] = hashlib.sha256(raw).hexdigest()
    manifest = {'status': 'complete', 'collected_at': completed, 'taxonomy': config['taxonomy'],
                'hashes': hashes, 'symbols': list(SYMBOLS), 'source': 'SEC submissions + Alpaca assets/corporate actions',
                'announcement_times': 'not established; process_date is not public time'}
    atomic_json(directory/'manifest.json', manifest)
    atomic_json(directory.parent/'latest.json', {'snapshot_directory': directory.name})
    return load_reference(root)
