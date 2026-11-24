# External provider review / disabled adapters

2026-11-24. The MVP calls **no external financial API**. The only enabled adapter is self-generated DemoProvider. A Provider protocol exists; it is not evidence that these external services are integrated. No paid subscription or financial-account access was used.

| Candidate / official source | Observed access / contract concern | QuantCore status |
|---|---|---|
| [Yahoo terms](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html) | retrieval returned999; unofficial scraping/API redistribution rights not established | disabled; no yfinance scrape |
| [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | submissions/XBRL official JSON; SEC identity/fair-access policy applies | not connected; contact User-Agent not configured |
| [FRED API](https://fred.stlouisfed.org/docs/api/fred/) | API key and series-specific data rights; vintage/release needed | not connected; pure vintage selector implemented |
| [OpenDART guide](https://opendart.fss.or.kr/guide/main.do) | official disclosure API and authentication-key management | no key; disabled |
| [KRX data](https://data.krx.co.kr/) | tool obtained no readable page; data licensing/access must be reviewed separately | disabled |
| [Alpha Vantage](https://www.alphavantage.co/support/) | API key and terms; access quotas/pricing depend on endpoint/plan | no key; disabled |
| [Alpaca market FAQ](https://docs.alpaca.markets/us/docs/market-data-faq) | market/feed entitlements, delay and redistribution vary by account | no keys imported from old project; disabled |
| [Massive docs](https://massive.com/docs) | REST/WS asset categories documented; actual entitlements and redistribution not established | disabled |
| [Binance REST](https://developers.binance.com/en/docs/products/spot/rest-api) | request-weight/rate-limit policy; regional/access conditions must be reviewed | disabled; no exchange account access |
| [CoinGecko docs](https://docs.coingecko.com/) | demo/pro access methods documented, quotas depend on plan | no key; disabled |
| [한국투자 Open API](https://openapi.koreainvestment.com/) | browser retrieval failed; account/key/market-data permissions unverified | disabled |
| [Interactive Brokers API](https://www.interactivebrokers.com/campus/ibkr-api-page/) | brokerage/API access and market-data subscriptions require user configuration | disabled |

Provider-specific numeric pricing, exact current rate quotas and commercial redistribution licenses are **not fully verified** for these candidates; documentation links alone do not supply those permissions. They remain a prerequisite for enabling each real adapter, with source, feed delay, timezone, corporate actions, release/vintage, request limiter and retries recorded explicitly. Demo rate limiting (10ms scheduling gap / concurrency3) is a local workload setting, not an external provider entitlement.
