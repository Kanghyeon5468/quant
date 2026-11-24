# API reference

Local API: http://127.0.0.1:8100 · interactive schema `/docs` · read-only research domain.
If configured, send `Authorization: Bearer $QUANTCORE_API_TOKEN`. Next dashboard proxies private token server-side.

| Method/path | Behavior |
|---|---|
| GET /health | process/data mode readiness after bootstrap |
| GET /api/overview | fictional assets, dataset range/version, DAG state |
| GET /api/assets/{symbol}/prices?limit=252&as_of=UTC | OHLCV, provenance, quality; availability-filtered |
| GET /api/assets/{symbol}/indicators | causal indicator history with units |
| GET /api/assets/{symbol}/fundamentals?as_of=UTC | available financial ratios and exact formula metadata |
| GET/POST /api/factors | default scores or supplied nonnegative weights/sector_neutral |
| GET /api/backtests/{symbol}?strategy=momentum | momentum/mean_reversion/buy_hold with ledger and benchmark |
| GET /api/portfolio?method=minimum_variance&max_weight=.4 | optimizer plus independent risk report |
| GET /api/ml/{symbol} | Ridge/baseline walk-forward and split audit |
| GET /api/statistics | covariance/correlation, OLS/Huber/PCA, block bootstrap |
| GET /api/research/{symbol} | calculation-grounded report; LLM=false |
| POST /api/valuation | DCFAssumptions, sensitivity and seeded Monte Carlo |
| POST /api/options | European Black-Scholes price and Greeks |
| GET /api/monitoring | sampled latency quantiles, source storage, queue/cache/limitations |
| POST /api/ws-ticket | single-use 30-second ticket |
| WS /ws/market?ticket=... | historical dataset snapshots every 5s, allowed Origin required |

Unknown assets return404; invalid/infeasible inputs422; missing auth401; rate cap429. NaN values serialize as JSON null. Available-at filtering is applied before analysis. Data source/mode is explicit; no synthetic price is labeled realtime.
