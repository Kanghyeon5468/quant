# Known issues and unimplemented scope

## Data and financial validity
- Only deterministic synthetic USD daily equities are connected. Other asset classes are schema categories, not acquired datasets. No actual-market backtest is reported.
- Weekday calendar has no exchange holidays/DST or intraday ticks. Daily volume is not a reconstructed order book. Real market impact, short borrow, funding and trading calendars require separate implementation.
- Financial data is annual, fictional and nonfinancial. No XBRL taxonomy reconciliation, TTM, revised-vintage financial backtest or real statement verification. CCC/Altman/Piotroski/Beneish remain explicitly unsupported.
- DCF is an assumption calculator; WACC is supplied, not estimated. Only growth is randomized in Monte Carlo; it is not a calibrated joint distribution or company forecast.
- Fixed synthetic reference market caps are used in factor value scores. Only 6 assets; cross-sectional results are too small for institutional factor validation.
- Full technical set includes a labeled rolling **VWAP proxy**. No true tick VWAP, multitimeframe exchange aggregation or future-dependent Ichimoku lagging feature.
- Portfolio optimization is an in-sample allocation calculation. No out-of-sample rebalancing policy test. Historical crisis stress data and FX/rate exposures are absent.

## Engineering / security
- SQLite is the local authority. Bar revisions fail explicitly; a full immutable bitemporal market store is not implemented. Financial revisions are separately retained and availability-filtered.
- DAG currently maintains prices and marked portfolio value; other analytical modules use batch/cached computation. Stabilization still visits graph topology; graph benchmarks depend on workload.
- Event/HTTP latency metrics are in-memory bounded samples, not durable telemetry or a distributed SLO. WebSocket send duration is not network round-trip latency.
- Optional bearer token is a single researcher API capability; dashboard BFF assumes a local trusted user. No multi-user auth/RBAC/SSO, public deployment, persistent/distributed rate limits or production backup retention.
- No deep learning, SHAP, Optuna, MLflow, LLM/RAG, actual news/SEC providers, macro feeds, options surface or live brokerage route.
- Some installed Starlette versions warn that httpx-based TestClient is deprecated. The recorded tests still execute; upgrading the test transport can be planned separately.
- Initial Docker build stalled in the local `docker-credential-desktop get` helper. Public images were built using a temporary anonymous Docker config, leaving user credentials unchanged. This environment issue may require the same documented fallback.

## Remaining validation
Statement coverage refers to `quantcore` and `apps/api`, not frontend or development scripts. Property examples are not independent real-market evidence. Browser and Docker execution have separate measured records. p99.9 calculated from small local samples cannot guarantee production tail latency.

See [requirements_comparison.md](requirements_comparison.md) for the entire original requirement scope and MVP boundary.
