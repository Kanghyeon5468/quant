# Research tools

The dashboard's **연구 도구** tab exposes the additional analytics. The user can pin a tool and expand it alongside the active panel. Source, observation time, units, and the calculation basis appear with results. The browser uses the existing authenticated API proxy.

| Tool | Inputs and interpretation |
|---|---|
| Macro and FX | FRED publishes GDP, CPI, core PCE, payrolls, unemployment, effective Fed funds, Treasury 2Y/10Y, USD/KRW, and WTI spot. Refresh preserves immutable fetched snapshots. These are current-revision series. KRX prices and trading do not use the reference FX quote. The Federal Reserve publishes the FOMC calendar. The BLS calendar reports its own collection status. |
| Crypto | Coinbase BTC-USD and ETH-USD completed daily candles, observed L2 top ten and up to fifty recent trades. The live toggle subscribes to the public Exchange Level 2 batch and matches channels. It rebuilds order depth after reconnect and displays exchange and receipt times. |
| Imported markets | Use a licensed CSV with `timestamp,available_at,open,high,low,close,volume` and a metadata JSON with `symbol,name,asset_class,currency,exchange_timezone,source,volume_unit,license_note`. The importer validates source metadata, chronology, OHLC and duplicates before a versioned write. The imported universe is exposed through the research view. |
| Valuation | Comparable SEC TTM multiples, FCFF input data, WACC, FCFE, dividend discount, residual income, reverse DCF and SOTP. Forecasts and missing company inputs are user assumptions. The Monte Carlo interval varies the modeled revenue-growth assumption. Forward multiples require consensus or analyst forecasts. |
| Financial scores | Cash conversion cycle, the original public-manufacturer Altman Z, and explicitly labeled TTM proxies for Piotroski F and Beneish M. A missing source field yields an unavailable score when the formula requires it. |
| Technical and factors | Daily/weekly/monthly, loaded-universe breadth, relative strength, and IEX regular-session VWAP weighted from verified raw minute values. The last weekly/monthly bucket can be in progress. Factor validation uses next-observed-open holding periods, Rank IC, ICIR, groups and membership turnover. Current size/SIC residuals require enough independent exposures for the sample size. |
| Statistics and ML | ADF, KPSS, Engle–Granger and directional Granger tests, ARIMA(1,0,1), Kalman local level, Gaussian Markov regimes and GARCH(1,1). ML runs a nested chronological validation with an embargo, linear/regularized baselines, random forest, histogram boosting and a compact MLP. Reports include fold scores, feature shifts, experiment fingerprint and exact linear Ridge attribution with a training-mean background. |
| Basket replay | Cross-sectional momentum, a long-only pairs rotation, volatility-targeted slots and an SPY slot enter the existing minute limit-fill simulation after the last visible signal. Results use the existing independent risk filter. |
| Options and brief | Explicit-assumption European option prices, Greeks and implied volatility. The brief compares SEC calculations, reuses verified Claude excerpts and displays template hypotheses with the metrics to check in later filings. |

## Data refresh and local experiments

The existing information worker can refresh public macro and Coinbase snapshots every six hours through `configs/information.json`. Use the individual CLI to refresh one public source. Provider calls are GETs. The historical execution engine reads local sources.

```bash
PYTHONPATH=. .venv/bin/python scripts/collect_macro.py
PYTHONPATH=. .venv/bin/python scripts/collect_crypto.py
PYTHONPATH=. .venv/bin/python scripts/import_market_bars.py instrument.json bars.csv
PYTHONPATH=. .venv/bin/python scripts/run_ml_experiment.py AAPL
```

The ML command stores the experiment and source dataset version under ignored `artifacts/research/experiments`. The API's optional account configuration accepts an environment JSON map from lowercase SHA-256 hashes of random API keys to `viewer` or `researcher`. Set `QUANTCORE_API_USERS_JSON` on the API and `QUANTCORE_WEB_SIGN_IN=true` on the Next server to use individual login. A viewer can read research snapshots and establish a WebSocket session. A researcher can also submit calculations and view the local paper account. Keep the plaintext keys with the users who receive them. This configuration is for the local server. An authenticated `GET /api/metrics` exposes current-process timings in Prometheus text format. The actual portfolio engine maintains the rolling sample covariance across overlapping snapshot updates and rebuilds after a changed overlap.

The optional Compose telemetry container stores minute observations and query failures for 30 days in ignored `artifacts/research_telemetry/monitoring.sqlite3`. It uses the configured API token or an optional viewer token from `QUANTCORE_MONITOR_TOKEN`.

```bash
mkdir -p artifacts/research_telemetry
docker compose -f docker-compose.yml -f docker-compose.alpaca.yml -f docker-compose.telemetry.yml up -d telemetry
docker compose -f docker-compose.yml -f docker-compose.alpaca.yml -f docker-compose.telemetry.yml stop telemetry
```

## Remaining inputs

- Source credentials, entitlements or licensed files for additional exchanges, full bond/FX/commodity markets, and tradable futures and options chains. The import view shows each supplied dataset's provenance and validation state.
- The BLS feed returned HTTP 403. The separately sourced Federal Reserve calendar is available. Historical first-release macro vintage data, an earnings call text/audio archive, and time-stamped consensus data have separate source requirements.
- Broader historical listings, verified borrow/funding quotes, timestamped historical financial and sector universes, and sufficient independent validation periods are needed for the remaining strategies and larger model claims. The current issuer risk groups come from SEC SIC, and the 13F universe comes from the existing collectors.
- Production retention, high concurrency tests against the intended deployment, and provisioning/review of individual accounts require a target environment.

Provider specifications and statistical methods are documented by [FRED](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html), [BLS](https://www.bls.gov/help/hlpiCAL.htm), [Federal Reserve](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm), [Coinbase Exchange](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles), [SEC EDGAR](https://www.sec.gov/search-filings/edgar-application-programming-interfaces), and [statsmodels](https://www.statsmodels.org/stable/tsa.html).

Dependencies added to execute audited time-series models were statsmodels (stationarity, cointegration, Granger, state-space and ARIMA) and arch (GARCH maximum-likelihood fit). The lock records their tested runtime and required transitive dependencies.
