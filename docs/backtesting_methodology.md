# Backtesting methodology

Data: deterministic synthetic daily OHLCV, seed 20261124, 6 fictional nonfinancial USD equities, 780 weekdays from 2023-01-02 to 2025-12-26. Evaluate the final 252 bars. This does not establish real-market profitability, survivorship robustness or exchange-specific execution quality.

Strategies implement `targets(frame)` using information through each completed close:

| Strategy | Rule | Target |
|---|---|---|
| momentum | close > 60-bar SMA | 95%; otherwise 0 |
| mean_reversion | 20-bar z-score < -1 enters; z-score >=0 exits | hold 95% until exit |
| buy_hold | constant target | 95% benchmark, daily rebalance toward target |

A signal from the previous close executes at the next synthetic open (bar completion minus 6h30). If the previous bar is not available before execution, reject. This is a fixed synthetic UTC calendar; it must be replaced for real markets. Maximum execution participation is 1% of **previous completed bar** volume, avoiding same-day full-volume foresight. Unfilled quantity expires and the next target is recalculated.

Each fill uses price = open×[1±(slippage 2bp + half spread 1bp + 5bp×sqrt(quantity/previous volume))]. Commission = notional×1bp. Cost terms are applied per fill, not a fixed round-trip charge. Zero-cost results rerun the same strategy/liquidity rules with all cost coefficients zero; resulting share counts may differ.

Integer shares, Decimal cash rounded to 0.0001 USD, weighted-average acquisition basis including commission. Partial sale realized P&L includes allocated basis. Win rate/profit factor are based on closed sell fills, not necessarily complete round-trip episodes. Initial cash $100,000. No borrowing, leverage, shorting, funding or borrow fees; these are unsupported, not assumed verified at zero. Positions remaining at end are marked to final close; no forced final liquidation.

Corporate actions have explicit handlers: split adjusts inventory/basis, dividend credits cash, delisting settles with supplied recovery and stops new trades. Fractional split entitlements require a cash-in-lieu price and currently fail. Synthetic demo contains no corporate actions; unit scenarios exercise handlers. Real action-adjusted strategy signals, actual delisting universe and announcement timing remain unvalidated.

Annualization 252 bars/year and rf=0. Drawdown includes initial equity. CAGR, annual volatility, Sharpe/Sortino/Calmar, duration, turnover, win rate/profit factor, alpha/beta, tracking error and information ratio are generated. Alpha is arithmetic daily regression-style annualization, not causal attribution. Benchmark-relative return = strategy wealth/benchmark wealth−1.

No result-driven parameter tuning. Two fixed strategies on all six symbols are reported including losses. Multiple strategy/symbol results are not independent validation or an optimized investable portfolio.
