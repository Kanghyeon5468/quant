# System design decisions

- Python 3.12 virtualenv is isolated from previous projects. No existing API keys or market archives were imported.
- Fictional QALPHA/QBETA/QGAMMA/QDELTA/QEPSILON/QZETA share a synthetic market factor plus seeded independent shocks. Daily business-day calendar includes weekdays without exchange holiday/DST modeling. All are USD nonfinancial equities.
- SQLite WAL and SQLAlchemy bound statements provide transaction isolation and uniqueness. A changed existing bar is rejected; silent historical overwrites are prohibited. Fundamental amendments use immutable content hashes and latest-known selection per accounting period.
- Parquet is a snapshot; SQLite is the authority if export fails. Data manifest includes hash/source/range. No Redis is necessary for 4,680 rows.
- Async I/O is applied to provider orchestration; numerical functions run in FastAPI worker threads. This does not claim process-parallel numerical execution.
- Repeated backtests/indicators/portfolio computations use bounded `lru_cache`. Immutable dataset version means these caches need no live invalidation; a changed dataset requires a new service instance.
- Generated demo returns and terminal-value assumptions are not claims about real companies or market returns.
- WebSocket emits the same historical dataset snapshot every five seconds. It is a functioning data channel, not a real-time exchange feed.
- Financial modules are usable without HTTP/UI. Missing inputs cause null/not-applicable states or explicit errors.
- Docker services use nonroot users and bind published ports to 127.0.0.1. A gateway with user authentication/TLS is required before any remote deployment.
