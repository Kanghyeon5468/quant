import numpy as np
from scipy.optimize import minimize


def optimize(returns, method='minimum_variance', max_weight=.4, *, observed_covariance=None):
    if not 0 < max_weight <= 1 or returns.shape[1]*max_weight < 1-1e-10:
        raise ValueError('infeasible maximum weight')
    if len(returns) < 3 or not np.isfinite(returns.to_numpy()).all():
        raise ValueError('finite aligned return history required')
    n = returns.shape[1]
    observed = returns.cov().to_numpy() if observed_covariance is None else np.asarray(observed_covariance)
    if observed.shape != (n, n) or not np.isfinite(observed).all():
        raise ValueError('finite covariance matrix required')
    covariance = observed*252+np.eye(n)*1e-10
    initial = np.full(n, 1/n)
    if method == 'equal_weight':
        weights = initial
    else:
        def objective(w):
            if method == 'minimum_variance':
                return float(w@covariance@w)
            if method == 'risk_parity':
                contributions = w*(covariance@w)
                return float(np.sum((contributions/contributions.sum()-1/n)**2))
            raise ValueError('unsupported optimizer')
        result = minimize(objective, initial, method='SLSQP', bounds=[(0, max_weight)]*n,
            constraints=[{'type': 'eq', 'fun': lambda w: w.sum()-1}], options={'ftol': 1e-12, 'maxiter': 1000})
        if not result.success:
            raise ValueError('optimization failed: '+result.message)
        weights = result.x
    if abs(weights.sum()-1) > 1e-7 or weights.min() < -1e-8 or weights.max() > max_weight+1e-8:
        raise ValueError('optimizer violated constraints')
    variance = float(weights@covariance@weights)
    contributions = weights*(covariance@weights)/variance
    return {'method': method, 'weights': dict(zip(returns.columns, weights.tolist())),
        'risk_contribution': dict(zip(returns.columns, contributions.tolist())),
        'annualized_volatility': float(np.sqrt(variance)), 'max_weight': max_weight,
        'in_sample': True, 'constraints': 'long-only; fully invested; position cap', 'status': 'converged'}
