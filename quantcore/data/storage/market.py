"""Read-only actual market repository shared by API analytics and paper snapshots."""
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

import numpy as np
import pandas as pd

from quantcore.core.models import Bar
from quantcore.data.errors import DataUnavailable
from quantcore.data.providers.alpaca import SYMBOLS, corporate_actions, load_snapshot


@dataclass(frozen=True)
class MarketSnapshot:
    version: str
    frames: dict
    actions: dict
    metadata: dict


class MarketRepository:
    def __init__(self, directory):
        self.directory = Path(directory)
        self._fingerprint, self._snapshot = None, None
        self._lock = RLock()

    def _sources(self):
        sources, fingerprint = [], []
        for kind in ('real_equities', 'paper_equities'):
            pointer = self.directory/kind/'latest.json'
            if not pointer.exists():
                continue
            # Snapshot names are portable across host/container mount points.
            raw = pointer.read_bytes()
            name = Path(json.loads(raw)['snapshot_directory']).name
            if name in ('', '.', '..'):
                raise ValueError('invalid actual snapshot name')
            target = pointer.parent/name
            manifest = json.loads((target/'manifest.json').read_text())
            signatures = []
            for filename in ('manifest.json', 'prices.parquet', 'actions.json', 'calendar.csv'):
                stat = (target/filename).stat()
                signatures.append((filename, stat.st_size, stat.st_mtime_ns))
            fingerprint.append((kind, raw, signatures))
            sources.append((kind, target, manifest))
        if not sources:
            raise DataUnavailable('Alpaca snapshot missing. Collect actual data first; no synthetic fallback.')
        return sources, repr(fingerprint)

    def load(self):
        with self._lock:
            try:
                sources, fingerprint = self._sources()
                if fingerprint == self._fingerprint:
                    return self._snapshot
                frames, payload, lineage = [], {}, []
                for kind, path, _ in sources:
                    frame, _, manifest = load_snapshot(path)
                    if manifest.get('source') != 'alpaca-iex-regular-1min' or manifest.get('feed') != 'iex':
                        raise ValueError('unexpected actual source/feed')
                    if set(frame.symbol) != set(SYMBOLS) or frame.duplicated(['symbol', 'session']).any():
                        raise ValueError('missing universe or duplicate actual session')
                    for _, row in frame.iterrows():
                        Bar.model_validate({k: row[k] for k in Bar.model_fields if k in frame.columns})
                    if frames:
                        prior = pd.concat(frames).drop_duplicates(['symbol', 'session'], keep='last')
                        overlap = prior.merge(frame, on=['symbol', 'session'], suffixes=('_old', '_new'))
                        for field in ('open', 'high', 'low', 'close', 'volume'):
                            if not np.allclose(overlap[field+'_old'], overlap[field+'_new'], rtol=0, atol=1e-10):
                                raise ValueError('actual bar revision conflict; explicit version review required')
                        for field in ('timestamp', 'available_at', 'execution_open'):
                            if not (overlap[field+'_old'] == overlap[field+'_new']).all():
                                raise ValueError('actual session timing conflict')
                    frames.append(frame)
                    for action_kind, rows in json.loads((path/'actions.json').read_text()).items():
                        bucket = payload.setdefault(action_kind, {})
                        for row in rows:
                            if row['id'] in bucket and bucket[row['id']] != row:
                                raise ValueError('corporate action revision conflict')
                            bucket[row['id']] = row
                    lineage.append({'kind': kind, 'snapshot_id': path.name, 'hashes': manifest['hashes'],
                                    'collected_at': manifest['collected_at']})
                data = pd.concat(frames).drop_duplicates(['symbol', 'session'], keep='last').sort_values(['symbol', 'timestamp'])
                if data.available_at.max() > pd.Timestamp.now(tz='UTC'):
                    raise ValueError('actual snapshot contains future bars')
                actions = corporate_actions({k: list(v.values()) for k, v in payload.items()},
                                            data.session.min(), data.session.max())
                groups = {}
                for symbol, group in data.groupby('symbol', sort=True):
                    group = group.set_index('timestamp').sort_index().copy()
                    factor = np.ones(len(group))
                    for action in actions[symbol]:
                        if action.kind == 'split':
                            factor[group.index >= action.effective_at] *= action.value
                    group['signal_close'] = group.close.to_numpy()*factor
                    groups[symbol] = group
                version = hashlib.sha256(json.dumps(lineage, sort_keys=True).encode()).hexdigest()[:16]
                metadata = {'mode': 'historical', 'source': 'alpaca-iex-regular-1min', 'feed': 'iex',
                    'currency': 'USD', 'timeframe': '1Day', 'dataset_version': version, 'lineage': lineage,
                    'as_of': data.timestamp.max().isoformat(), 'available_at': data.available_at.max().isoformat(),
                    'rows': len(data), 'sessions': len(data.session.unique()),
                    'paper_snapshot_id': next((x['snapshot_id'] for x in lineage if x['kind'] == 'paper_equities'), None)}
                if self._sources()[1] != fingerprint:
                    raise ValueError('actual inputs changed during read; retry the request')
                snapshot = MarketSnapshot(version, groups, actions, metadata)
                self._snapshot, self._fingerprint = snapshot, fingerprint
                return snapshot
            except DataUnavailable:
                raise
            except (ValueError, KeyError, OSError, TypeError) as error:
                raise DataUnavailable('Actual market data unavailable: '+str(error)) from None
