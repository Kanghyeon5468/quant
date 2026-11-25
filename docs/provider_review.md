# External provider review / disabled adapters

Updated2026-11-25: the original MVP used only DemoProvider. The user explicitly authorized reading the prior stock project's Alpaca settings for market-data GET requests. A new read-only Alpaca adapter collected a separate actual-data snapshot for the real-equity CLI/notebook. No old dataset, account endpoint, order call or paid subscription was used. Other providers remain disabled.

Later on2026-11-25 the user explicitly requested paper trading with that connection. A separate paper-only client successfully queried the simulated account and submitted two simulated equity orders. This extends the original task scope; the data adapter remains GET-only. The trading host is fixed to paper-api.alpaca.markets, no live-money API or paid subscription is used, and all raw account/order data stays local. See PAPER_TRADING.md and paper_trading_results.json.

| Candidate / official source | Observed access / contract concern | QuantCore status |
|---|---|---|
| [Yahoo terms](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html) | retrieval returned999; unofficial scraping/API redistribution rights not established | disabled; no yfinance scrape |
| [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | submissions/XBRL official JSON; SEC identity/fair-access policy applies | not connected; contact User-Agent not configured |
| [FRED API](https://fred.stlouisfed.org/docs/api/fred/) | API key and series-specific data rights; vintage/release needed | not connected; pure vintage selector implemented |
| [OpenDART guide](https://opendart.fss.or.kr/guide/main.do) | official disclosure API and authentication-key management | no key; disabled |
| [KRX data](https://data.krx.co.kr/) | tool obtained no readable page; data licensing/access must be reviewed separately | disabled |
| [Alpha Vantage](https://www.alphavantage.co/support/) | API key and terms; access quotas/pricing depend on endpoint/plan | no key; disabled |
| [Alpaca market FAQ](https://docs.alpaca.markets/us/docs/market-data-faq) | explicit user authorization; IEX bars and corporate actions returned200; raw data retained locally for personal research | enabled for GET market-data only; fresh1Min archive and separate regular-session snapshot |
| [Massive docs](https://massive.com/docs) | REST/WS asset categories documented; actual entitlements and redistribution not established | disabled |
| [Binance REST](https://developers.binance.com/en/docs/products/spot/rest-api) | request-weight/rate-limit policy; regional/access conditions must be reviewed | disabled; no exchange account access |
| [CoinGecko docs](https://docs.coingecko.com/) | demo/pro access methods documented, quotas depend on plan | no key; disabled |
| [한국투자 Open API](https://openapi.koreainvestment.com/) | browser retrieval failed; account/key/market-data permissions unverified | disabled |
| [Interactive Brokers API](https://www.interactivebrokers.com/campus/ibkr-api-page/) | brokerage/API access and market-data subscriptions require user configuration | disabled |

Provider-specific numeric pricing, exact current rate quotas and commercial redistribution licenses are **not fully verified** for these candidates; documentation links alone do not supply those permissions. They remain a prerequisite for enabling each real adapter, with source, feed delay, timezone, corporate actions, release/vintage, request limiter and retries recorded explicitly. Demo rate limiting (10ms scheduling gap / concurrency3) is a local workload setting, not an external provider entitlement.

Actual Alpaca collection uses a0.6s minimum request gap, bounded retries for network/5xx and stops on401/403/429. Only data.alpaca.markets /v2/stocks/bars and /v1/corporate-actions GET paths are permitted. [Actual methodology/results](REAL_STOCK_BACKTEST.md). Public Alpha Vantage demo probes returned an Information message instead of a full actual series; no such response was treated as data. Yahoo/Stooq access restrictions were not bypassed.

## Actual analysis API connection · 2026-11-25

Alpaca historical and paper rolling snapshots now feed a read-only MarketRepository and ActualResearchService. The API/browser receive no Alpaca credentials; source collection remains on the host. A direct authorized GET of the last completed AAPL regular-session minute matched the deployed API reference price. All15 actual backtest returns matched saved results exactly; host/container/web dataset versions matched. See actual_api_validation.json. Actual fundamentals/news/filings remain disconnected; the app does not infer them from prices.
