# Risk methodology

Portfolio returns use the last 252 aligned synthetic daily observations. Optimizers: equal weight, minimum variance (SLSQP), equal-risk-contribution (SLSQP). Constraints: long-only, sum=1, maximum weight default 40%. Check feasibility before optimization and inspect success/constraints after optimization. No silent equal-weight fallback after a solver failure.

Covariance: sample daily covariance×252 + 1e-10 diagonal regularization. Risk contribution share = w_i(Σw)_i/(w'Σw). Weights and risk are **in-sample estimates**, not a backtest of the optimization policy.

Historical VaRα = empirical α-quantile of losses −r; Expected Shortfall = mean losses at/above that quantile. Parametric VaR = −mean + Φ⁻¹(α)×sample sigma. Monte Carlo VaR uses 10,000 iid Gaussian draws, seed42; fat tails/serial dependence are not modeled. Negative VaR for a profitable lower tail is not floored to zero.

Concentration HHI=Σw², gross/net exposures and correlation matrix are reported. Individual weight >40% produces a concentration alert in the independent risk function. Two **hypothetical** scenarios are labeled: −30% equity shock and doubled volatility. No 2008/2020/2022 historical stress is claimed.

Black-Scholes assumes European exercise, no dividends, constant rate/volatility. Greeks expose Vega/Rho per one percentage point and Theta per calendar day. Brent root-finding supplies IV and fails for unbracketed prices. No market volatility surface, American exercise or FX/rate hedge model.
