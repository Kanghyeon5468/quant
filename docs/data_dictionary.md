# Data dictionary

| Field | Meaning / validation |
|---|---|
| symbol | uppercase 1–20 characters, immutable asset identity |
| asset_class | equity/ETF/index/bond/FX/commodity/crypto/future/option schema categories; demo data only equity |
| timestamp | UTC completed daily bar time, 21:00 in demo |
| available_at | UTC time information became usable, never before bar completion |
| open/high/low/close | finite positive raw USD/share quotes, valid high/low envelope |
| volume | nonnegative integer shares per synthetic daily bar |
| currency | USD or KRW contract; current dataset USD only; no implicit FX conversion |
| source / mode | demo:`quantcore-synthetic-v1` / `synthetic`; separate actual notebook:`alpaca-iex-regular-1min` / `historical`; no realtime claim |
| period_end | annual accounting period, not availability time |
| published_at | financial statement disclosure time |
| financial available_at | disclosure/processing availability; normalized UTC |
| financial source_url | null for synthetic data, never a fabricated filing link |
| unit | financial currency must match amount units |
| reference market_cap | fixed synthetic USD reference cap, not today's real cap projected into history |
| target weight | long-only fraction [0,max_weight], created at completed close |
| fill | next synthetic daily open; integer quantity; recorded cost and exact cash string |
| total_return | compounded whole evaluation window, not per-day return |
| VaR/ES | one synthetic business-day loss fraction at specified confidence |

Risk and technical numbers use IEEE float64; cash bookkeeping uses Decimal with 0.0001 USD rounding and integer inventory. Float equivalence tests use 1e-10/1e-12 tolerances where applicable. Rounding artifacts are not counted as economic alpha.
