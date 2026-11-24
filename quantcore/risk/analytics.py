import numpy as np
from scipy.stats import norm


def risk_report(returns, weights, confidence=.95, seed=42):
    if not .5 < confidence < 1:
        raise ValueError('confidence must be between .5 and 1')
    w = np.asarray(weights, dtype=float)
    data = returns.to_numpy(dtype=float)
    if data.ndim != 2 or data.shape[1] != len(w) or len(data) < 3 or not np.isfinite(data).all() or not np.isfinite(w).all():
        raise ValueError('finite matching weights and return matrix required')
    if (w < 0).any() or abs(w.sum()-1) > 1e-8:
        raise ValueError('long-only weights summing to one required')
    portfolio = data@w
    losses = -portfolio
    var = float(np.quantile(losses, confidence))
    tail = losses[losses >= var]
    sigma = float(portfolio.std(ddof=1))
    draws = np.random.default_rng(seed).normal(portfolio.mean(), sigma, 10000)
    equity = np.r_[1., np.cumprod(1+portfolio)]
    return {'confidence': confidence, 'horizon': 'one synthetic business day',
        'historical_var': var, 'expected_shortfall': float(tail.mean()),
        'parametric_var': float(-portfolio.mean()+norm.ppf(confidence)*sigma),
        'monte_carlo_var': float(np.quantile(-draws, confidence)), 'monte_carlo_assumption': 'iid Gaussian; seed 42',
        'annualized_volatility': sigma*np.sqrt(252),
        'max_drawdown': float((equity/np.maximum.accumulate(equity)-1).min()),
        'concentration_hhi': float(w@w), 'gross_exposure': float(abs(w).sum()),
        'net_exposure': float(w.sum()), 'correlation': returns.corr().to_numpy().tolist(),
        'assets': list(returns.columns), 'currency': 'USD', 'mode': 'synthetic',
        'stress_tests': [{'name': 'Hypothetical equity crash', 'kind': 'hypothetical', 'portfolio_return': -.3*float(w.sum())},
                         {'name': 'Hypothetical volatility x2', 'kind': 'hypothetical', 'annualized_volatility': sigma*np.sqrt(252)*2}],
        'alerts': ['concentration_limit'] if w.max() > .4+1e-8 else []}
