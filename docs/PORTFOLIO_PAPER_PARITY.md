# Portfolio replay and paper risk · 2026-11-25 (KST)

## Scope and common policy

`quantcore/strategies/orders.py` supplies the same target sizing, cash reservation, DAY limit prices and cost assumptions to paper and the portfolio replay. `quantcore/risk/limits.py` is an independent pretrade filter. Existing per-symbol backtests remain available and are a different experiment.

- One $100,000 cash ledger; AAPL/MSFT/NVDA/TSLA/SPY, five fixed $20,000 slots. An active signal targets $19,000 divided by the buy limit, rounded down to whole shares. Allocation follows that stable symbol order; it is not an optimizer.
- The existing daily Momentum rule compares available split-neutral close to SMA60. A completed close can only create an order for a later session. Market value and sizing use raw prices. Profit is not automatically spread across larger slots.
- Buy limit = prior close ×1.01 rounded up to cents; sell limit = prior close ×0.99 rounded down. DAY / regular-session only. No cash credit for an unfilled sell; pending buys reserve their remaining limit notional plus modeled commission. No margin/shorting.
- Common costs: commission1bp, slippage2bp, half of spread2bp, impact5bp × sqrt(order quantity / preceding ADV20). Replay records actual modeled fill commission and price friction. Paper records separate estimated costs in the journal; it does not falsify broker balances or subtract modeled slippage again from broker execution P&L. Historical net results are not broker net returns.
- Replay limits fills to1% of each observed IEX minute's volume and respects price limits/OHLC bounds. Remaining quantity expires at the regular close. An OHLC touch is modeled at the completed minute's end; unobserved minutes are not manufactured. Intraday marks carry only until the next observed bar.
- Alpaca paper uses its own NBBO matching and partial-fill rules. It does not reproduce live queue priority or all trading costs and does not credit dividends. This replay therefore excludes dividends, while the original economic per-symbol backtest continues to include its documented dividend assumptions. [Official paper documentation](https://docs.alpaca.markets/us/docs/paper-trading), [order documentation](https://docs.alpaca.markets/us/docs/orders-at-alpaca).
- The current verified sample has no splits. The portfolio loader explicitly stops if a split requires an inventory migration; it does not silently mishandle shares. Paper already stops on an upcoming split requiring refreshed references.

## Independent risk rules

Defaults are in `configs/risk_limits.json`; common order settings are in `configs/order_policy.json`. The local journal can override each filename. Configuration hashes are recorded. Defaults are initial operating assumptions, not fitted or optimized parameters.

| Rule | Default / basis |
|---|---|
| Daily loss | 2% of previous-close strategy NAV; halt persists through the New York date |
| Drawdown | 10% from activation high-watermark, sampled every5 minutes; explicit reset required |
| Total long exposure | 95% of strategy NAV, including pending buys at limit prices |
| Per-symbol exposure | 20% of strategy NAV |
| Sector concentration | 40%; unavailable sector data is one UNCLASSIFIED group |
| Correlation concentration | 40% per connected group with pairwise positive correlation ≥0.8; previous60 session returns |
| Portfolio volatility | 25% annualized; previous20-session standard deviations and60-session correlation, sqrt(wᵀΣw) |
| Liquidity | New + remaining pending buy shares ≤1% of preceding20-session mean IEX daily volume |

The engine trims integer buy quantities, rejects infeasible entries, and cancels only the program's own pending buys on a breach. No new order can follow an unconfirmed cancellation. Existing owned-share exits remain permitted. There is **no forced liquidation**; losses can exceed thresholds between checks or while a position is still held. Broker position ownership, cash and deduplication checks remain in place.

Missing/unreadable/stale risk inputs block buys and make own pending buys cancellation candidates. This includes invalid broker equity/marks, missing60-session history and a stale completed-session snapshot. Exchange-close collection has a10-minute grace. No risk success is inferred from absent data. No automatic outbound email/chat notifications were added: SQLite alerts are deduplicated by New York date, policy, rule and symbol, and shown in the local dashboard with freshness.

Sector data is genuinely unavailable. All five instruments share UNCLASSIFIED; ETF holdings are not looked through. The measured historical restrictions mainly reflect this conservative40% group cap and20% position cap. It is not a sector-aware institutional classifier.

Risk NAV = current approved budget + broker equity − broker equity when risk tracking activated. Previous-close NAV uses Alpaca `last_equity`; peak and loss latches survive restarts. An explicitly audited budget adjustment shifts the baseline, rather than masquerading as profit. External deposits/withdrawals or account resets require manual review; no automated cash-flow attribution is claimed.

## Executed actual-data results

Frozen snapshot `20261125T013853Z`, original70 response pages verified by uncompressed SHA-256;683,312 observed regular-session minute rows reconcile to1,770 daily rows /354 sessions. Evaluation is252 sessions, **2025-11-24–2026-11-24**; earlier observations provide warmup. No new paid feed or raw-data redistribution.

| Whole-account scenario | Net return | Final NAV | Daily-close max drawdown | Annualized realized volatility | Mean invested weight |
|---|---:|---:|---:|---:|---:|
| Momentum, common order rules, risk filter off | -5.56% | $94,442.28 | -12.67% | 12.01% | 55.76% |
| Momentum, risk filter on | -5.75% | $94,245.44 | -9.27% | 7.78% | 31.72% |
| Momentum, risk on, modeled costs set to zero | -4.79% | $95,208.54 | -9.03% | 7.77% | 31.88% |
| Always-active five-slot benchmark, common costs, risk off | +7.99% | $107,989.86 | -15.79% | 21.10% | 88.93% |

The always-active benchmark rebalances to fixed nominal slot targets; it is not a constant-share buy-and-hold. The zero-cost case independently reruns sizing and fills: it is not net return plus fees, and its orders can differ. All cases start with the same total capital; these are not sums of independent $100,000 symbol accounts.

Risk lowered daily-close drawdown by3.41 percentage points and realized volatility by4.23 points, while return fell0.20 points. This single historical sample does **not** establish improved profitability. The risk case produced230 fill events,7 expirations,5 risk cancellations and634 deduplicated day/symbol/rule alerts (141 position,493 unclassified-sector). Its commission was $111.09 and modeled execution friction $257.04. Daily-loss/drawdown latches did not trigger in this actual sample; those paths were verified with controlled adverse-price/broker tests.

Independent ledger replay reconciles every daily cash balance, whole-share inventory and marked NAV. All modeled fills occur after signal availability and satisfy their limit. Remaining limitations include selected surviving large caps, a single IEX venue, historical revisions collected now, no original real-time publication archive, no after-hours or order-book evidence, and no taxes/interest.

Machine-readable derived results: [portfolio_backtest_results.json](portfolio_backtest_results.json). Detailed local fills/orders remain under ignored `artifacts/portfolio_replay/report.json`.

## Viewing and operation

- [Portfolio notebook](../notebooks/QuantCore_Portfolio_Paper_Backtest.ipynb): saved tables, equity/drawdown curves, invested weight/cash and audit; JSON rather than version-sensitive pandas pickle.
- [Local dashboard](http://localhost:3100): strategy/backtest view includes whole-account comparison; system/settings includes paper risk status and alerts. Previous per-symbol views remain.
- `GET /api/portfolio-backtest` and `GET /api/paper-risk` are read-only, use existing authentication, and never receive broker credentials or the private journal. Only derived/public projections are mounted. Risk output older than10 minutes is flagged stale; a missing report is unavailable.

```bash
make portfolio-backtest           # local frozen minute replay; no broker/network
make portfolio-notebook-check    # execute notebook and save outputs
make real-dashboard              # actual cache + derived reports, readonly API mounts
.venv/bin/python scripts/manage_paper_automation.py pause
.venv/bin/python scripts/manage_paper_automation.py resume
# A drawdown latch is not cleared by resume. Review while paused, then explicitly:
.venv/bin/python scripts/manage_paper_automation.py risk-reset --reason "reviewed cause and approved a new peak"
```

STOP blocks new automatic orders and preserves existing broker orders; while operator-paused, automated risk cancellation is also paused. The explicit risk-reset keeps the daily-loss latch, resets the peak to the last observed risk NAV, and leaves an audit record. After resuming, a current broker check can immediately halt entries again. Do not delete the journal or change client IDs to bypass a halt.

Live activation and final executed checks are recorded in README/progress and `portfolio_paper_validation.json`. There is still no multi-day forward paper performance claim.
