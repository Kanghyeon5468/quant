# Paper performance monitoring · 2026-11-25 (KST)

The **모의투자 현황 / Paper performance** dashboard tab records the Alpaca paper account's actual observations and own-order executions. It does not treat accepted orders, deposits, historical simulations or modeled costs as realized trading profit.

## Data flow

The existing five-minute LaunchAgent completes trading/risk handling first, then invokes `collect_safely`. The collector allows only GET requests to the fixed paper host, extending the existing client with `/v2/account/portfolio/history` and `/v2/account/activities`. Account, clock and positions come from the same client. Paginated activities are bounded, deduplicated by provider ID, and retained locally. Failed performance collection is reported separately and never clears a trading/risk halt or aborts a completed risk check.

Data lives in the existing ignored `artifacts/paper_trading/journal.sqlite3`:

| Table | Meaning |
|---|---|
| `performance_meta` | Account identity guard, monitoring baseline and source refresh cursors |
| `performance_observations` | Actual equity/cash marks; one upsert per five-minute UTC bucket |
| `performance_history` | Provider daily account series, refreshed for the requested90-day window |
| `performance_activities` | Fill and nontrade events, keyed by provider ID |
| `performance_fetches` | Private source responses, SHA-256, source and collection time for provenance |
| `order_evidence` | Immutable signal, reference price, policy and evidence-capture time |
| `decision_runs` | Session/budget decision and risk-restriction snapshot |

Private account/activity/order identifiers stay in this journal. `artifacts/paper_performance_public/status.json` is a projection with selected fields and irreversible display keys. The API receives this directory read-only, without broker credentials or the private journal. `/api/paper-performance` uses existing API authentication, recursively removes private identifier fields, and has no POST/order operation. Missing inputs are unavailable. Reports older than600 seconds, reports from a future host time, or a newer failed collection are marked stale. Failed source refreshes retain old records with explicit unavailable source status; incomplete activity reconciliation produces unknown P&L rather than zero.

Host collection time and broker observation time are separate. Source timestamps retain UTC offsets; the screen formats its collection/evidence times in Asia/Seoul. No new dependency or API key was added.

## Financial definitions

- **Account equity/cash:** actual broker values. Daily equity change is `equity - last_equity`; monitoring change is current equity minus the first stored observation. These are labeled changes in equity, not cash-flow-adjusted investment returns.
- **Realized gross P&L:** replay actual own-order FILL events in timestamp order using a long-only weighted-average cost ledger. Sales recognize `sold shares × (sale price - average cost)`. Remaining inventory is marked using broker current prices for unrealized gross P&L. Order cumulative fill quantities and current position quantities must reconcile before reporting these totals.
- **Nontrade activities:** cash deposits/withdrawals/journals are tracked separately and never added to own-fill trading profit. Known cash income/charges are not silently allocated as strategy profit. Unknown stock/corporate/reorganization events require review and suppress P&L totals. External/unmanaged fills likewise make attribution incomplete. This is not a complete tax or corporate-action accounting system.
- **Fill rates:** filled shares / submitted requested shares, and fully filled orders / submitted orders. Canceled submitted orders remain in the denominator. The default view selects the current approved budget revision; prior small-budget cancellations can be included with the checkbox.
- **First-fill elapsed time:** first actual fill event minus broker submission time, when both exist. This includes overnight market closure; it is not network/exchange latency.
- **Reference price change:** signed adverse change from previous-close reference to actual weighted fill price, in basis points (positive worse). Opening gaps are included. No quote-at-submission data exists, so this must not be called pure execution slippage.
- **Modeled comparison:** the recorded prior-close cost formula gives an illustrative adverse reference price and estimated cost for filled quantity. It is not a reconstructed next-minute backtest fill or an actual broker fee. Missing cost inputs are marked, and no estimate is deducted again from broker balances/P&L.

Signals/reference prices and policy evidence are stored before a new order's POST. Existing accepted AAPL53 / TSLA48 orders were backfilled from the verified available signal snapshot and explicitly marked **reconstructed_after_submission**. The earlier canceled2-share orders have no captured evidence and are displayed as unavailable; they are not given invented explanations.

## Historical comparison

The screen can show the provider's daily account history, including dates before this strategy/collector started. It excludes zero-equity unfunded intervals and preserves provider P&L/base-value fields rather than inventing a return through account funding. The recent observation chart contains only marks actually collected; no missing intervals are converted into fills or profit.

A separate comparison uses only dates shared by completed daily account history and the stored risk-enabled whole-account backtest, on/after monitoring began. At least two common dates are required. Each curve is normalized to100 on the common first date; original initial holdings, fills and funding assumptions may still differ. Cash-flow review, failed source fetches or incomplete attribution disable this comparison. At initial validation there was not enough common history, so the screen correctly displayed **동일 기간의 완료 일별 자료가 아직 없습니다.** No multi-day forward profitability is claimed.

## Operation

Open [localhost dashboard](http://localhost:3100) and select **모의투자 현황** (keyboard9). The collector runs every five minutes through the existing LaunchAgent, and the screen reloads the projection every30 seconds. Mac login, network access and normal scheduler operation are still required. Collection runs even when automatic new orders are paused, as long as the scheduler can query the account.

For an explicit read-only refresh:

```bash
.venv/bin/python scripts/collect_paper_performance.py --env-file /authorized/path/.env
```

`QUANTCORE_PAPER_PERFORMANCE_DIR` sets the API projection directory (default `artifacts/paper_performance_public`). `docker-compose.alpaca.yml` mounts only the projection at `/paper-performance:ro`. Demo mode always returns unavailable and does not expose the local paper account. External notification delivery and always-on hosting are outside this change.

Final measured counts, source status and background/browser verification are saved in `paper_performance_validation.json` and README/progress. Source activities and raw account history are private and ignored by Git.

Official references: [Portfolio history](https://docs.alpaca.markets/us/reference/getaccountportfoliohistory-1), [activities and pagination](https://docs.alpaca.markets/us/reference/getaccountactivities-2), [activity fields/types](https://docs.alpaca.markets/us/docs/account-activities).

The frozen historical backtest report is not automatically rerun by this collector. Updating that report with a new matching evaluation period is required before new forward paper dates can appear in the historical comparison; the account observations themselves continue to accumulate automatically.
