# Chronological portfolio validation · 2026-11-25 (KST)

This research adds period separation to the existing actual-minute, single-account replay. It does not change the automatic paper strategy or claim profitable trading.

## Frozen protocol

`configs/walk_forward.json` was frozen before the run. Plan SHA-256: `4fbe11514b1509901efdce69eec537956ef7ec771fb0ea6d7b00553fa599ff4a`.

Input is the same verified70 original response pages /683,312 RTH minutes /354 exchange sessions. The first90 sessions warm indicators; the remaining264 sessions support two walk-forward test windows and one reserved final42-session window. Candidates are fixed Momentum60, Momentum40, Momentum90 and Mean Reversion20. The highest prior validation Sharpe (rf0) wins; ties follow the fixed candidate list. No additional candidates/thresholds were chosen after seeing the OOS results.

These are fixed trading rules, without fitted ML weights. Expanding training history supplies causal development/indicator context and a training diagnostic. The following42-session validation window selects the lookback/rule. It is not a claim that a predictive ML estimator was trained. The selector accepts only past training/validation dates and rejects observations unavailable at the selection cutoff. The first next-window execution occurs after that cutoff.

| Window | Development/training history | Selection validation | Subsequent evaluation | Selected rule | Selected evaluation return |
|---|---|---|---|---|---:|
| 1 | 2025-11-06–2026-03-26 | 2026-03-27–2026-05-27 | 2026-05-28–2026-07-28 | Momentum40 | -2.54% |
| 2 | 2025-11-06–2026-05-27 | 2026-05-28–2026-07-28 | 2026-07-29–2026-09-25 | Momentum90 | +1.20% |
| Final reserve | 2025-11-06–2026-07-28 | 2026-07-29–2026-09-25 | 2026-09-28–2026-11-24 | Mean Reversion20 | -2.48% |

The first two evaluations have42 sessions each; the final reserve has42 sessions. The continuous evaluated period is **126 sessions,2026-05-28–2026-11-24**. Prior test observations can become past validation data for the next decision; they cannot influence their own earlier selection.

**The archive was already used in earlier whole-period reports.** The final reserve is excluded from this selection pipeline but is not a genuinely unseen external holdout. Its interpretation must remain retrospective. Forward paper observations provide the future unseen evaluation.

## One portfolio and common assumptions

The selected schedule is executed through one continuous $100,000 cash/inventory ledger; independent candidate returns are not spliced together as if they were one account. Holdings, cash and risk latches survive strategy switches and fold boundaries. The benchmark/fixed-rule cases start with the same capital on the same evaluation date and use the same DAY limits, whole shares, cost model and risk settings. The always-active benchmark is fixed-slot rebalancing, not constant-share buy-and-hold.

Current SEC groups were observed only after the historical cutoff. All these cases therefore use the same conservative historical UNCLASSIFIED40% group cap; current classifications are not inserted retroactively. This differs from the current live sourced grouping for a legitimate availability reason, not a hidden parameter change.

The cost-stress case doubles commission/slippage/spread/impact while keeping the already-selected schedule. It does not re-optimize strategy choice after seeing stressed evaluation returns.

| Continuous account scenario | Net return | Final NAV | Daily-close max drawdown | Mean invested weight |
|---|---:|---:|---:|---:|
| Selected by prior validation | -3.82% | $96,180.52 | -9.88% | 31.65% |
| Fixed Momentum60 | -3.51% | $96,486.17 | -7.37% | 36.92% |
| Always-active slots, same risk | +4.73% | $104,727.66 | -6.88% | 39.94% |
| Selected schedule, doubled costs | -4.01% | $95,985.70 | -10.06% | 31.68% |

The selection procedure underperformed fixed Momentum60 by0.31 percentage points in this sample and had greater drawdown. It does not justify replacing the live strategy. Selected-case commission was$69.76 and modeled execution friction$159.38. All losses are retained.

A paired circular5-session block bootstrap (2,000 seeded samples) gives a conditional95% interval of approximately **-9.18 to+9.18 percentage points** for the selected-minus-fixed total-return difference. This is a small-sample uncertainty diagnostic, not a selection-adjusted significance claim or proof of outperformance. The universe is only five currently selected instruments, the feed is IEX, and no historical-revision/complete-survivorship archive is established.

## Verification and viewing

The actual run independently reconciled cash, whole-share holdings and marked NAV. Signal availability precedes fills, modeled limit prices are respected, and strategy changes do not reset the account. Tests verify that changing later prices/strategy schedules does not change earlier selections/fills and that test windows remain disjoint. Existing252-session portfolio scenarios were rerun with maximum numerical metric difference **0**.

[Saved notebook](../notebooks/QuantCore_Walk_Forward_Validation.ipynb) contains the period table, timeline, equity/drawdown graphs, per-scenario audit and limitations. It executed4 code cells,2 PNG outputs and0 errors. JSON is used instead of pandas/joblib persistence. The default view reads the saved report; optional replay uses local authorized raw pages and does not call a broker.

The dashboard strategy/backtest view shows the same results through authenticated read-only GET `/api/walk-forward`. Raw source data and detailed local fills remain under ignored datasets/artifacts; `walk_forward_results.json` contains derived results only.

```bash
make walk-forward
.venv/bin/python scripts/execute_walk_forward_notebook.py
```

The live paper strategy remains the previously authorized Momentum60. Final test/browser/activation records are in `reference_validation.json` and `walk_forward_notebook_validation.json`.
