# Database schema

`datasets/quantcore.sqlite3` uses WAL and SQLAlchemy metadata creation.

| Table | Primary/unique key | Payload |
|---|---|---|
| assets | symbol | validated asset JSON |
| bars | integer id; unique(symbol,timestamp) | UTC available_at, SHA-256, validated JSON |
| fundamentals | SHA-256 id | symbol, available_at, immutable accounting JSON |
| audit_log | integer id | UTC time, event kind, structured JSON |

Bar duplicates are idempotent; conflicting contents roll back the entire batch. Corrections require an explicit versioned bar provider, not an overwrite. Financial revisions coexist; queries select only known revisions then latest revision per accounting period.

Parquet `prices.parquet` includes typed UTC timestamps and raw OHLCV/provenance. `manifest.json` binds row count, range, source and hash. No external SQL text is accepted; symbol and Parquet paths are bound parameters. No production schema migration chain has been applied yet; schema version 0.1 creation is the MVP baseline.

Backup: `python scripts/backup.py datasets/quantcore.sqlite3 /new/location/backup.sqlite3`. SQLite's online backup API includes WAL state, runs integrity_check and writes a checksum. Restore by stopping the API and restoring into a fresh data directory, then re-export Parquet; never replace a running database.
