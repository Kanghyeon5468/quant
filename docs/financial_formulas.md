# Financial formulas and applicability

All figures are calculated in Python. The demo uses fictional annual USD nonfinancial-company statements. Disclosure/availability/period/source/formula travel with every financial metric. Real taxonomy mapping, segment consolidation and TTM construction are unimplemented.

| Metric | Definition | Conditions / limits |
|---|---|---|
| revenue/EPS/FCF growth | (current−prior)/prior | same annual basis, positive prior; negative/zero prior yields null |
| EPS | net income/shares | positive shares; simplified period shares, no diluted weighted-average EPS reconstruction |
| gross/operating/net margin | corresponding profit/revenue | positive revenue |
| EBITDA | EBIT + depreciation/amortization | fields must be present; not GAAP cash flow |
| FCF | operating cash flow−capex | capex is positive cash outflow; no automatic company-specific adjustments |
| ROE/ROA | net income/average beginning-and-ending equity/assets | prior period required; positive denominator |
| ROIC | EBIT×(1−tax)/(equity+debt−cash) | nonfinancial company; end-period capital approximation, not full invested-capital reconstruction |
| leverage/current/interest coverage | debt/equity; current assets/current liabilities; EBIT/interest | nonfinancial applicability; positive denominator |
| accrual ratio | (net income−CFO)/average assets | cash-flow accrual proxy |
| asset turnover | revenue/average assets | prior period required |
| dilution | (shares_now−shares_prior)/shares_prior | synthetic issued shares, not option dilution modeling |
| FCFF_t | revenue_t×margin×(1−tax)+D&A−capex−ΔNWC | user/model assumptions explicitly supplied |
| DCF EV | Σ FCFF_t/(1+WACC)^t + TV/(1+WACC)^N | WACC > terminal g; fixed assumptions, no actual forecast claim |
| TV | FCFF_(N+1)/(WACC−g) | terminal working-capital change recomputed at terminal g |
| equity/share | (EV−net debt)/shares | positive share count; negative equity possible |
| factor z-score | (winsorized value−cross-sectional mean)/population std | 5/95% clipping; constant cross section becomes zero |
| 12−1 momentum | close[t−21]/close[t−252]−1 | 253 bars; approximately 21 weekdays/month |
| sample volatility | std(daily returns,ddof1)×sqrt252 | synthetic weekday annualization |
| CAGR | (ending/initial)^(252/n)−1 | valuation window n bars |
| Sharpe | mean(r)/std(r,ddof1)×sqrt252 | rf=0; null when no variance |
| Sortino | mean(r)/sqrt(mean(min(r,0)^2))×sqrt252 | all periods in downside denominator |
| maximum drawdown | min(equity/running_peak−1) | initial capital is part of peak history |
| historical VaR/ES | quantile(loss,α); mean(loss≥VaR) | empirical sample; no tail guarantee |
| minimum variance | minimize w'Σw | Σ regularized, long-only/fully invested/capped |
| risk contribution | w_i(Σw)_i/(w'Σw) | covariance model dependent |
| Black-Scholes | C=SΦ(d1)−Ke^(−rT)Φ(d2); d1=[ln(S/K)+(r+σ²/2)T]/(σ√T) | European/non-dividend; d2=d1−σ√T |

Technical calculations: SMA arithmetic window mean; EMA adjust=False; WMA linear 1..n weights; RSI/ATR/ADX use Wilder smoothing seeded by n-value SMA. Bollinger=20-SMA±2 population standard deviations. OBV accumulates signed volume. Stochastic uses rolling high/low. Ichimoku leading spans displayed with a **past-data positive shift**; future-dependent lagging span is not supplied as a feature. VWAP is explicitly a **20-bar typical-price×volume proxy**, not true intraday transaction VWAP.

Reference sources: [Damodaran valuation materials](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/valuation.html), [SciPy SLSQP](https://docs.scipy.org/doc/scipy/reference/optimize.minimize-slsqp.html), [scikit-learn time-series validation](https://scikit-learn.org/stable/modules/cross_validation.html#time-series-split). Formula definitions and deliberate approximations above are the implementation contract; references do not certify model forecasts or returns. DCF perpetuity, indicator constant/trending series, option put-call parity and known 10.45058357 call price are checked independently.
