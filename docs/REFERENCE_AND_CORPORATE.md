# Sourced classification and corporate accounting · 2026-11-25 (KST)

## Current instrument identities and risk groups

Five SEC submissions endpoints were actually fetched and matched by CIK/ticker with Alpaca's asset records. Provider responses, instrument identifiers, SIC, collection time and SHA-256 are retained in versioned private `datasets/reference/` snapshots. A latest pointer is published only after all required responses validate. A failed/forbidden request never replaces that pointer or bypasses access controls. Automatic refresh is daily; no new paid service/API key is used.

| Instrument | CIK | SEC SIC | Current project risk group |
|---|---:|---:|---|
| AAPL | 320193 | 3571 Electronic Computers | TECHNOLOGY |
| MSFT | 789019 | 7372 Prepackaged Software | TECHNOLOGY |
| NVDA | 1045810 | 3674 Semiconductors | TECHNOLOGY |
| TSLA | 1318605 | 3711 Motor Vehicles | AUTOMOTIVE |
| SPY | 884394 | Not supplied | EQUITY_ETF, verified against issuer |

The broad grouping is declared in `configs/security_master.json` and is **derived from SIC, not licensed GICS**. SPY is an ETF, not an operating company assigned a fictitious sector. Its internal holdings are not looked through. Group concentration still uses the existing40% limit; position20%, correlation40%, volatility25%, cash and loss gates remain.

The live guard chooses a classification vintage available at its cutoff (and no older than90 days). Missing/expired observations fall back to UNCLASSIFIED. Current data is never backdated into a historical test. This archive's price evaluation ends2026-11-24, before the current classifications were collected, so the walk-forward experiment correctly keeps the historical UNCLASSIFIED40% group cap. Manual local risk assignments remain explicit overrides.

Official sources: [SEC submissions APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces), [SIC definitions](https://www.sec.gov/search-filings/standard-industrial-classification-sic-code-list), [SPY issuer](https://www.ssga.com/us/en/individual/etfs/state-street-spdr-sp-500-etf-trust-spy).

## Actual corporate source collection

Queried Alpaca corporate actions from2020-01-01 through60 days beyond collection for the five symbols. The verified snapshot contains **5 splits,111 cash dividends,0 name/symbol changes and2 related cash mergers**. A merger returned because one instrument was the acquirer is associated with its acquiree, rather than wrongly changing the acquirer's shareholder quantity. These two mergers do not represent a direct split/dividend entitlement in the current owned universe.

Sources include process/effective/ex/payment dates where provided. Original public announcement times are not established; `process_date` is **not** treated as publication time. Collection availability is recorded separately. These events are mechanical accounting inputs, not announcement-based predictive features. Source rows and version hashes remain private, without API headers/credentials. [Official endpoint and availability caveat](https://docs.alpaca.markets/us/reference/corporateactions-1).

## Shared event book and broker reconciliation

`quantcore/accounting/corporate.py` replays actual own FILL events and sourced corporate events in timestamp order. At the same opening timestamp, the corporate event precedes new fills: a purchase on the ex-date open does not acquire yesterday's dividend entitlement.

- **Forward/reverse split:** quantity changes by the verified ratio, total cost basis remains unchanged, and average unit cost changes accordingly. This cannot create profit by itself. Subsequent sales use the adjusted average cost. The paper runner reads separately audited quantity adjustments; original trade intents/fills are not overwritten. IDs prevent repeated application. Corrections that would change an already-applied adjustment halt trading for review.
- **Liquidity units:** preceding volume is converted to current split-share units before live ADV/cost calculations. Before the first post-split daily bar, a verified applied split supplies the known ratio; after the new bar the cumulative split factor supplies it, without double adjustment. Existing upcoming-split/reference-price gates require fresh references before placing new orders.
- **Dividend rights:** record eligible quantity at the ex-date and expected gross income. Payment is matched to actual DIV/withholding/fee activities by instrument and payment date. Missing payment is pending/not credited, not a successful cash receipt. No synthetic cash is added to the broker account or counted as trading P&L. Own-fill gross P&L and received income remain distinct.
- **Name/symbol change:** the event book transfers quantity and cost to the new symbol and checks broker positions. A new ticker still requires verified market-universe/identity migration before this fixed-universe paper trader resumes. This is deliberately not an unattended expansion of the authorized tradable universe.
- **Fractional shares/cash in lieu and unsupported reorganizations:** retain the entitlement/review state and block new trading when reconciliation is incomplete. The implementation does not guess rounding, a cash-in-lieu price, or an unknown new security identity.
- **Pending orders:** identify and cancel only this journal's affected orders before an effective split/symbol change. Final broker cancellation must be confirmed; an unresolved cancellation blocks further orders. No account-wide cancel or liquidation is added.

Corporate preflight runs before the existing broker ownership/risk path. It cross-checks recorded cumulative fill quantities, event-adjusted inventory and actual positions. Unknown activity, mismatched shares or unverified migration produces a review-required report and trading halt. The separate performance collector uses the same event book, so its average-cost P&L does not disagree with a valid split-adjusted position.

`Journal` was moved into `paper/journal.py` for use by both paths, maintaining the same SQLite file/schema and compatibility imports from the old runner. Shared atomic JSON publication moved into `core/files.py`; module-cycle tests pass.

## Scope of actual verification

At activation, the account still had **0 owned shares**, with AAPL53 and TSLA48 accepted/0filled. Therefore the actual account required **0 quantity/cash adjustments and0 corporate cancellations**. Real source access and live reconciliation were verified; split/dividend/symbol-change behavior was tested with controlled broker/fill fixtures. No real symbol change occurred in the collected universe.

The current historical minute archive has0 splits. The new portfolio replay still explicitly stops on a historical split requiring its own execution-ledger migration; the older independent economic backtest retains its existing split/dividend implementation. Do not describe the paper event-book tests as a demonstrated historical split execution in the new portfolio replay.

View source groups and current reconciliation in **모의투자 현황**, or GET `/api/corporate-actions`. The API mounts only a read-only public projection. Missing/stale/review states remain visible. The operating budget and original order IDs are preserved.

```bash
# Project .env: SEC_USER_AGENT="App name real-contact@example.com"
.venv/bin/python scripts/collect_reference_data.py --env-file /authorized/path/.env
```

Final tests, activation and measured live state are in `reference_validation.json`, README and progress.
