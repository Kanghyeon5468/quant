# Known issues and unimplemented scope

## Data and financial validity
- The API/dashboard now support explicit demo and actual Alpaca modes. The running localhost deployment uses actual AAPL/MSFT/NVDA/TSLA/SPY snapshots, including paper rolling updates; base keyless Compose and the original notebook remain synthetic. Actual fundamentals, sector/market cap, additional markets and a full historical tradable universe remain absent. Actual financial/factor views report missing inputs.
- Synthetic calendar remains weekdays. Actual equities use XNYS holidays/DST/early closes and regular-session1Min aggregation. IEX is not consolidated SIP; modeled fills, volume limits and costs do not reconstruct an order book. Short borrow/funding remain unsupported.
- Financial data is annual, fictional and nonfinancial. No XBRL taxonomy reconciliation, TTM, revised-vintage financial backtest or real statement verification. CCC/Altman/Piotroski/Beneish remain explicitly unsupported.
- DCF is an assumption calculator; WACC is supplied, not estimated. Only growth is randomized in Monte Carlo; it is not a calibrated joint distribution or company forecast.
- Fixed synthetic reference market caps are used in factor value scores. Only 6 assets; cross-sectional results are too small for institutional factor validation.
- Full technical set includes a labeled rolling **VWAP proxy**. No true tick VWAP, multitimeframe exchange aggregation or future-dependent Ichimoku lagging feature.
- Portfolio optimization is an in-sample allocation calculation. No out-of-sample rebalancing policy test. Historical crisis stress data and FX/rate exposures are absent.

## Engineering / security
- SQLite is the local authority. Bar revisions fail explicitly; a full immutable bitemporal market store is not implemented. Financial revisions are separately retained and availability-filtered.
- The actual analysis repository merges compatible frozen/rolling snapshots read-only. Conflicting overlap/corporate-action revisions return503 and require explicit review; no automatic revision reconciliation or silent last-write-wins exists. Real API analytics are version-cached batch calculations, not a full analytical DAG. The current actual ML comparison has only1 fold/29 observations per model and is not paper-trading input.
- DAG currently maintains prices and marked portfolio value; other analytical modules use batch/cached computation. Stabilization still visits graph topology; graph benchmarks depend on workload.
- Event/HTTP latency metrics are in-memory bounded samples, not durable telemetry or a distributed SLO. WebSocket send duration is not network round-trip latency.
- Optional bearer token is a single researcher API capability; dashboard BFF assumes a local trusted user. No multi-user auth/RBAC/SSO, public deployment, persistent/distributed rate limits or production backup retention.
- No deep learning, SHAP, Optuna, MLflow, LLM/RAG, actual news/SEC providers, macro feeds, options surface or live brokerage route.
- A separate opt-in Alpaca paper CLI was added2026-11-25. Its first two orders were accepted outside market hours with0 filled shares at the recorded check. A subsequent request added incremental refresh and a5-minute local scheduler; its operating state and OS permission requirements are recorded in PAPER_AUTOMATION.md. No multi-day forward paper-return history exists yet. Paper quote-based fills omit some live costs and may differ from the historical engine; see PAPER_TRADING.md.
- Some installed Starlette versions warn that httpx-based TestClient is deprecated. The recorded tests still execute; upgrading the test transport can be planned separately.
- Initial Docker build stalled in the local `docker-credential-desktop get` helper. Public images were built using a temporary anonymous Docker config, leaving user credentials unchanged. This environment issue may require the same documented fallback.

## Remaining validation
Statement coverage refers to `quantcore` and `apps/api`, not frontend or development scripts. Property examples are not independent real-market evidence. Browser and Docker execution have separate measured records. p99.9 calculated from small local samples cannot guarantee production tail latency.

See [requirements_comparison.md](requirements_comparison.md) for the entire original requirement scope and MVP boundary.

## Portfolio/paper convergence — 2026-11-25
A separate shared-policy whole-account replay and independent paper risk gate now exist; see [PORTFOLIO_PAPER_PARITY.md](PORTFOLIO_PAPER_PARITY.md). Broker NBBO fills and balances remain distinct from minute-OHLC modeled net returns. Sector data is still absent (UNCLASSIFIED40% cap), no ETF look-through, and split migration is fail-closed in the new replay. Daily/drawdown limits block entry/cancel pending buys rather than guaranteeing a maximum loss or forcibly liquidating. No multi-day forward profit claim or external alert delivery.

## Paper performance monitoring — 2026-11-25
Actual equity/activity collection and a read-only performance dashboard now exist; see [PAPER_PERFORMANCE.md](PAPER_PERFORMANCE.md). Initial actual verification still has0filled shares, so there is no multi-day forward strategy-return claim. Own-fill P&L is gross/average cost, not tax accounting; unsupported corporate actions require review. Same-date historical comparison requires an updated frozen backtest plus sufficient completed paper observations.

## Sourced classification/corporate and period separation — 2026-11-25
Current SEC-derived project risk groups and SPY issuer classification now exist; not GICS and no ETF look-through. Current observations cannot backfill historical classifications. Paper corporate accounting handles split-adjusted quantity/cost and dividend entitlement vs actual receipts; unverified new-ticker market migration/fractional cash-in-lieu/complex reorganization stop trading for review. Actual account still has0holdings/0fills at validation; corporate mechanics are controlled-fixture tested. The new historical portfolio replay still stops on an archive containing a split needing execution-ledger migration; its current input has0splits.
Chronological rule selection, two subsequent test windows and a retrospective final reserve now run on real minutes; selected strategy underperformed the fixed rule in126sessions. The archive had already been viewed; no genuinely unseen external holdout or profitability claim. Details:REFERENCE_AND_CORPORATE.md and WALK_FORWARD_VALIDATION.md.

### Actual information update — 2026-11-25
The earlier absence of SEC fundamentals/13F/news is superseded by [ACTUAL_INFORMATION.md](ACTUAL_INFORMATION.md). Current real coverage is partial: 49/68 financial metrics, two managers/four filings, 69 news articles. Earnings transcripts, LLM, SNS, current GICS, unverified ticker migration and fractional settlement remain unavailable. Existing historical performance has no retroactively injected current information.
