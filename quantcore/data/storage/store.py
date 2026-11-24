import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd
from sqlalchemy import Column, Integer, MetaData, String, Table, Text, UniqueConstraint, create_engine, select
from sqlalchemy.dialects.sqlite import insert

from quantcore.core.models import Asset, Bar

metadata = MetaData()
assets = Table('assets', metadata, Column('symbol', String, primary_key=True), Column('data', Text, nullable=False))
bars = Table('bars', metadata, Column('id', Integer, primary_key=True), Column('symbol', String, nullable=False),
    Column('timestamp', String, nullable=False), Column('available_at', String, nullable=False),
    Column('digest', String, nullable=False), Column('data', Text, nullable=False), UniqueConstraint('symbol', 'timestamp'))
facts = Table('fundamentals', metadata, Column('id', String, primary_key=True), Column('symbol', String),
    Column('available_at', String), Column('data', Text, nullable=False))
audits = Table('audit_log', metadata, Column('id', Integer, primary_key=True), Column('at', String),
    Column('kind', String), Column('data', Text))


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f'sqlite:///{self.directory / "quantcore.sqlite3"}',
                                    connect_args={'check_same_thread': False, 'timeout': 20})
        with self.engine.connect() as connection:
            connection.exec_driver_sql('PRAGMA journal_mode=WAL')
        metadata.create_all(self.engine)

    def save_asset(self, asset: Asset):
        with self.engine.begin() as c:
            c.execute(insert(assets).values(symbol=asset.symbol, data=asset.model_dump_json()).on_conflict_do_nothing())

    def asset_list(self):
        with self.engine.connect() as c:
            return [json.loads(r[0]) for r in c.execute(select(assets.c.data).order_by(assets.c.symbol))]

    def save_bars(self, records: list[Bar]):
        count = 0
        with self.engine.begin() as c:
            for bar in records:
                raw = bar.model_dump_json()
                digest = hashlib.sha256(raw.encode()).hexdigest()
                stamp = bar.timestamp.isoformat()
                old = c.execute(select(bars.c.digest).where(bars.c.symbol == bar.symbol, bars.c.timestamp == stamp)).scalar()
                if old and old != digest:
                    raise ValueError('immutable bar conflict: revisions need an explicit versioned provider')
                if not old:
                    c.execute(insert(bars).values(symbol=bar.symbol, timestamp=stamp, available_at=bar.available_at.isoformat(),
                                                 digest=digest, data=raw))
                    count += 1
        return count

    def prices(self, symbol, as_of=None):
        query = select(bars.c.data).where(bars.c.symbol == symbol).order_by(bars.c.timestamp)
        if as_of is not None:
            cutoff = pd.Timestamp(as_of)
            if cutoff.tzinfo is None:
                raise ValueError('as_of must be timezone-aware')
            query = query.where(bars.c.available_at <= cutoff.tz_convert('UTC').isoformat())
        with self.engine.connect() as c:
            rows = [json.loads(r[0]) for r in c.execute(query)]
        if not rows:
            return pd.DataFrame()
        frame = pd.DataFrame(rows)
        frame['timestamp'] = pd.to_datetime(frame.timestamp, utc=True)
        frame['available_at'] = pd.to_datetime(frame.available_at, utc=True)
        return frame.set_index('timestamp')

    def save_fundamentals(self, records):
        with self.engine.begin() as c:
            for original in records:
                row = original.copy()
                if row.get('currency') not in ('USD', 'KRW') or row.get('unit') != row['currency']:
                    raise ValueError('financial currency and unit required')
                for field in ('available_at', 'published_at'):
                    stamp = pd.Timestamp(row[field])
                    if stamp.tzinfo is None:
                        raise ValueError('financial timestamps must be timezone-aware')
                    row[field] = stamp.tz_convert('UTC').isoformat()
                if row['available_at'] < row['published_at']:
                    raise ValueError('facts available before disclosure')
                raw = json.dumps(row, sort_keys=True, allow_nan=False)
                key = hashlib.sha256(raw.encode()).hexdigest()
                c.execute(insert(facts).values(id=key, symbol=row['symbol'], available_at=row['available_at'], data=raw).on_conflict_do_nothing())

    def fundamentals(self, symbol, as_of):
        stamp = pd.Timestamp(as_of)
        if stamp.tzinfo is None:
            raise ValueError('as_of must be timezone-aware')
        with self.engine.connect() as c:
            rows = [json.loads(r[0]) for r in c.execute(select(facts.c.data).where(
                facts.c.symbol == symbol, facts.c.available_at <= stamp.tz_convert('UTC').isoformat()))]
        # Keep only the latest known revision of each period. Amendments must not
        # become the prior accounting period in a growth/average calculation.
        by_period = {}
        for row in sorted(rows, key=lambda r: r['available_at']):
            by_period[row['period_end']] = row
        return [by_period[period] for period in sorted(by_period)]

    def export_parquet(self):
        all_frames = [self.prices(a['symbol']).reset_index() for a in self.asset_list()]
        frame = pd.concat(all_frames, ignore_index=True)
        target = self.directory/'prices.parquet'
        tmp = target.with_suffix('.parquet.tmp')
        frame.to_parquet(tmp, index=False)
        os.replace(tmp, target)
        manifest = {'mode': 'synthetic', 'rows': len(frame), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                    'source': sorted(frame.source.unique()), 'start': str(frame.timestamp.min()), 'end': str(frame.timestamp.max())}
        (self.directory/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
        return manifest

    def parquet_summary(self):
        path = self.directory/'prices.parquet'
        if not path.exists():
            return []
        with duckdb.connect() as c:
            rows = c.execute('SELECT symbol,count(*) n,min(close) low,max(close) high FROM read_parquet(?) GROUP BY symbol ORDER BY symbol', [str(path)]).fetchall()
        return [dict(zip(['symbol', 'rows', 'min_close', 'max_close'], row)) for row in rows]

    def audit(self, kind, payload):
        with self.engine.begin() as c:
            c.execute(insert(audits).values(at=datetime.now(timezone.utc).isoformat(), kind=kind,
                                           data=json.dumps(payload, sort_keys=True, allow_nan=False)))
