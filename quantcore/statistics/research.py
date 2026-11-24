import numpy as np
from sklearn.decomposition import PCA
from sklearn.linear_model import HuberRegressor, LinearRegression


def benjamini_hochberg(pvalues):
    values = np.asarray(pvalues, dtype=float)
    if values.ndim != 1 or len(values) == 0 or not np.isfinite(values).all() or ((values < 0) | (values > 1)).any():
        raise ValueError('nonempty finite p-values in [0,1] required')
    order = np.argsort(values)
    adjusted = np.minimum.accumulate((values[order]*len(values)/np.arange(1, len(values)+1))[::-1])[::-1]
    result = np.empty(len(values))
    result[order] = np.minimum(adjusted, 1)
    return result.tolist()


def statistical_report(returns, seed=42):
    data = returns.to_numpy(dtype=float)
    if len(data) < 30 or data.shape[1] < 2 or not np.isfinite(data).all():
        raise ValueError('30 aligned finite returns and >=2 assets required')
    y, x = data[:, 0], data[:, 1:]
    linear = LinearRegression().fit(x, y)
    robust = HuberRegressor(max_iter=1000).fit(x, y)
    pca = PCA().fit(data)
    # Moving-block bootstrap preserves short serial dependence, unlike iid rows.
    rng = np.random.default_rng(seed)
    block, samples = 5, []
    for _ in range(1000):
        starts = rng.integers(0, len(y)-block+1, int(np.ceil(len(y)/block)))
        sampled = np.concatenate([y[s:s+block] for s in starts])[:len(y)]
        samples.append(sampled.mean())
    return {'assets': list(returns.columns), 'observations': len(data),
        'mean_daily_return': returns.mean().to_dict(), 'covariance': returns.cov().to_numpy().tolist(),
        'correlation': returns.corr().to_numpy().tolist(),
        'ols_in_sample_r2': float(linear.score(x, y)), 'robust_coefficients': robust.coef_.tolist(),
        'pca_explained_variance_ratio': pca.explained_variance_ratio_.tolist(),
        'first_asset_bootstrap_mean_95ci': np.quantile(samples, [.025, .975]).tolist(),
        'bootstrap': {'method': 'moving block', 'block_bars': block, 'samples': 1000, 'seed': seed},
        'mode': 'synthetic', 'limitations': ['in-sample dependence analysis; not causal', 'no GARCH/ARIMA/HMM in MVP']}
