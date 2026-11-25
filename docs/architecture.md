# Architecture

QuantCore is a modular monolith. Python 3.12 runs the data and numerical engine; FastAPI exposes a research-only API. Next.js serves the dashboard and proxies API requests. SQLite is authoritative; Parquet is an atomic analytical snapshot queried with DuckDB.

```mermaid
flowchart LR
  Demo[Seeded demo provider] --> Ingestion[Async ingestion / validation]
  Ingestion --> SQL[(SQLite / SQLAlchemy)]
  SQL --> PQ[(Parquet / DuckDB)]
  Ingestion --> Events[Bounded event bus]
  Events --> DAG[Incremental DAG / portfolio mark]
  SQL --> Analytics[Financial / technical / factors]
  Analytics --> Research[Strategies / backtest / ML]
  SQL --> Risk[Optimization / independent risk]
  DAG --> API[FastAPI / WebSocket]
  Research --> API
  Risk --> API
  API --> Web[Next.js / React / ECharts]
  Alpaca[Authorized market-data GET] --> Frozen[Separate raw snapshot / hashes / XNYS aggregation]
  Frozen --> Real[Real-equity CLI / notebook]
  Real --> Research
```

Dependencies flow from `apps → research service → analytics/data → core`. Analytics do not import apps or the research service. Strategies produce target weights; the simulator owns execution/accounting. Risk does not depend on the optimizer. A source failure is isolated from other source tasks; event consumer failures are recorded and cannot silently create a successful startup.

The current production-style event path is demo batch → graph prices → individual marked values → portfolio value. Factor, technical and covariance calculations use cached/batch functions; the entire analytical stack is **not** yet an incrementally maintained DAG. Graph topology is checked using deterministic DFS each stabilization; large graph maintenance overhead remains to profile.

Alpaca actual-data collection is separate from the demo service and does not populate its SQLite/UI. Additional providers, distributed queues, Postgres/Timescale/Redis and heavy ML are deferred. This is a local research MVP, not a claim to reproduce Jane Street's internal architecture.
