# API reference

Local API: http://127.0.0.1:8100 · interactive schema `/docs` · read-only research domain.
If configured, send `Authorization: Bearer $QUANTCORE_API_TOKEN`. Next dashboard proxies private token server-side.

| Method/path | Behavior |
|---|---|
| GET /health | process/data mode readiness after bootstrap |
| GET /api/overview | selected demo/Alpaca assets, dataset range/version/provenance; demo DAG or actual session count |
| GET /api/assets/{symbol}/prices?limit=252&as_of=UTC | OHLCV, provenance, quality; availability-filtered |
| GET /api/assets/{symbol}/indicators | causal indicator history with units |
| GET /api/assets/{symbol}/signal | actual Momentum close/SMA60/target evidence; no order submission |
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

## Alpaca data mode

Set `QUANTCORE_DATA_SOURCE=alpaca` and `QUANTCORE_MARKET_DATA_DIR` to the directory containing `real_equities/` and/or `paper_equities/`. `make real-dashboard` mounts the host datasets read-only and enables this mode. Default base Compose remains demo. Actual mode has no broker credentials or account/order routes; it reads snapshots created by the authorized Alpaca collector, with no per-request external fetch.

Prices/indicators/backtests/portfolio/statistics/ML carry `mode=historical`, `source=alpaca-iex-regular-1min`, `dataset_version`, `as_of`, `available_at` and input `lineage`. The registry is AAPL/MSFT/NVDA/SPY/TSLA. Sector and market cap are null. Fundamentals return `status=missing`; the incomplete multifactor view returns `status=unavailable`. Short histories return `insufficient_history` rather than a fabricated backtest/ML result. Explicit actual mode with no cache fails bootstrap; corrupt/conflicting current input returns503 without demo fallback.

Indicator OHLC/volume are split-adjusted to the latest visible session units; raw quotes remain in the prices endpoint. SMA60 matches the paper rule at the reference close. Backtests remain independent-asset research simulations with modeled next-open costs, distinct from fixed-slot paper limit orders. Portfolio estimates are in-sample research allocations, not brokerage positions. ML evaluation does not create orders. Valuation/options endpoints remain explicit-assumption calculators and do not claim to retrieve actual financial statements.

WebSocket messages remain historical dataset snapshots. The actual source may update when the collector publishes a new snapshot; the version changes and the frontend refetches. Invalid input produces a `data_error` message while retaining the last visible basis date. This is not a streaming quote feed. Source gaps/revisions/collection latency and small ML evaluation samples remain documented limitations.

## Actual portfolio and paper risk reports

`GET /api/portfolio-backtest`: frozen whole-account four-scenario replay and policy/audit. `GET /api/paper-risk`: sanitized latest risk status, rules, concentration, local alerts and freshness (stale after600s). Both use existing API auth, return unavailable if absent/in demo mode, and have no POST/order operation. Report paths are `QUANTCORE_PORTFOLIO_REPORT_DIR` (default docs) and `QUANTCORE_PAPER_RISK_DIR` (default artifacts/paper_risk_public); Compose mounts only these projections read-only. See [policy and results](PORTFOLIO_PAPER_PARITY.md).

## Paper account performance

`GET /api/paper-performance`: actual account observations, provider daily equity history, average-cost own-fill gross P&L, execution/fill-rate statistics, submitted-order signal evidence, positions and a same-date backtest comparison when enough data exists. Read-only projection, existing authentication, no broker keys/private journal in API. Demo/missing files return unavailable; source failures and stale marks are explicit. Configure `QUANTCORE_PAPER_PERFORMANCE_DIR`. Definitions and caveats: [PAPER_PERFORMANCE.md](PAPER_PERFORMANCE.md).

The response also includes `risk` with the latest published risk status, check time and halt rules, and `llm_usage` with the UTC request cap, recorded Claude input/output counts and optional Anthropic token rate-limit observations. Usage aggregates come from the worker's local projection under the market data directory. The UTC daily request count includes failed and pending attempts. Token counts use reported usage. Remaining provider tokens carry the observation and refill timestamps for the reported per-minute limit.

## Sourced corporate reference and chronological validation

`GET /api/corporate-actions`: current sourced instrument/SIC project groups, corporate source counts, owned-event/dividend reconciliation, issues and freshness. `GET /api/walk-forward`: frozen chronological plan, train/validation/test selection tables, continuous OOS curves, same-risk benchmarks, doubled-cost stress and paired uncertainty. Both are authenticated read-only; demo/missing inputs return unavailable. `QUANTCORE_CORPORATE_DIR` controls the public corporate projection; the validation JSON uses the existing report directory. Raw account identifiers/keys are not exposed. See REFERENCE_AND_CORPORATE.md and WALK_FORWARD_VALIDATION.md.

### Actual information observations (2026-11-25)
- `GET /api/information?symbol=AAPL&as_of=<UTC>` returns sourced news metadata, deterministic keyword/numeric mentions and verified 13F changes. No generated summaries, transcript substitutes or LLM sentiment. News versions and reports unavailable at the cutoff remain absent.
- Actual fundamentals now use SEC CompanyFacts TTM and exact-period balance sheets; missing metrics remain null. `financial_source`, `financial_snapshot`, `collected_at`, `analyzed_at`, `available_at`, evidence tags/accessions and outstanding-share observation identify inputs. SPY remains missing.
- Actual factors use SEC + IEX on four eligible equities; SPY is excluded when selected financial factors are missing. GICS sector neutralization is unavailable. Factor calculation time and price observation time are distinct.
- The API process has no information-provider keys or outbound collection. See [operational details](ACTUAL_INFORMATION.md).

### Information allocation / official earnings / optional LLM
`GET /api/assets/{symbol}/signal` now includes information_analysis, effective_target_weight_within_slot and decision_policy_version. This is read-only preview; actual broker risk, inventory and policy-version checks remain in the paper worker. `GET /api/information` includes official earnings documents/comparisons, separate material/transcript availability, optional validated LLM claims and paper activation status. No credentials or full article/transcript bodies are exposed. LLM remains unconfigured at user request; missing model output is null, not synthetic sentiment. See INFORMATION_DECISIONS_AND_LLM.md.
