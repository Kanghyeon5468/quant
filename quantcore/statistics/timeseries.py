"""Bounded in-sample diagnostics on observed, aligned price histories."""
import warnings

import numpy as np
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression
from statsmodels.tsa.statespace.structural import UnobservedComponents
from statsmodels.tsa.stattools import acf, adfuller, coint, grangercausalitytests, kpss

from quantcore.statistics.research import benjamini_hochberg


def _safe(calculation):
    try:
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            output = calculation()
        if any("failed to converge" in str(w.message).lower() for w in captured):
            return {"status": "unavailable", "reason": "fit did not converge"}
        return {"status": "ok", **output}
    except (ValueError, TypeError, np.linalg.LinAlgError, FloatingPointError, RuntimeError, ZeroDivisionError) as error:
        return {"status": "unavailable", "reason": type(error).__name__}


def _test(fn, *args, **kwargs):
    result = fn(*args, **kwargs)
    return {"statistic": float(result[0]), "p_value": float(result[1])}


def _forecast(result):
    fit = getattr(result, "mle_retvals", {})
    if isinstance(fit, dict) and not fit.get("converged", True):
        raise ValueError("fit did not converge")
    return {"next_return": float(np.asarray(result.forecast(steps=1))[0]) / 100,
            "aic": float(result.aic)}


def _regime(returns):
    model = MarkovRegression(returns, k_regimes=2, trend="c", switching_variance=True)
    result = model.fit(disp=False, maxiter=150)
    if not result.mle_retvals.get("converged"):
        raise ValueError("regime fit did not converge")
    return {"filtered_probabilities": np.asarray(result.filtered_marginal_probabilities)[-1].tolist(),
            "state_means_pct": [float(result.params[model.param_names.index(f"const[{i}]")]) for i in range(2)],
            "aic": float(result.aic)}


def _garch(returns):
    from arch import arch_model

    model = arch_model(returns, mean="Constant", vol="GARCH", p=1, q=1, rescale=False)
    result = model.fit(disp="off", show_warning=False)
    if result.convergence_flag:
        raise ValueError("fit did not converge")
    variance = result.forecast(horizon=1, reindex=False).variance.iloc[-1, 0]
    return {"next_daily_volatility": float(np.sqrt(variance) / 100), "aic": float(result.aic)}


def _granger(first, second):
    fitted = grangercausalitytests(np.column_stack([first, second]), maxlag=[2])
    statistic, p_value, *_ = fitted[2][0]["ssr_ftest"]
    return {"statistic": float(statistic), "p_value": float(p_value), "lag": 2}


def diagnostics(prices, symbol, peer=None):
    symbols = [symbol] + ([peer] if peer is not None else [])
    clean = prices[symbols].dropna().tail(252)
    if len(clean) < 80 or not np.isfinite(clean.to_numpy()).all() or (clean <= 0).any().any():
        return {"status": "unavailable", "reason": "diagnostics require 80 aligned positive closes"}
    levels = np.log(clean.to_numpy())
    returns = np.diff(levels, axis=0) * 100
    target = returns[:, 0]
    result = {
        "status": "ok", "symbol": symbol, "peer": peer, "observations": len(clean),
        "basis": "last 252 aligned observed closes; log returns; in-sample",
        "tests": {
            "adf_log_price": _safe(lambda: _test(adfuller, levels[:, 0])),
            "kpss_log_price": _safe(lambda: _test(kpss, levels[:, 0], nlags="auto")),
        },
        "models": {
            "arima_1_0_1": _safe(lambda: _forecast(ARIMA(target, order=(1, 0, 1)).fit())),
            "kalman_local_level": _safe(lambda: _forecast(UnobservedComponents(target, level="local level").fit(disp=False))),
            "gaussian_markov_regimes": _safe(lambda: _regime(target)),
            "garch_1_1": _safe(lambda: _garch(target)),
        },
        "autocorrelation": _safe(lambda: {"lags_0_to_10": acf(target, nlags=10).tolist()}),
    }
    if peer:
        result["tests"]["cointegration"] = _safe(lambda: _test(coint, levels[:, 0], levels[:, 1]))
        pairs = [(symbols[a], symbols[b], _safe(lambda: _granger(returns[:, a], returns[:, b])))
                 for a, b in [(0, 1), (1, 0)]]
        valid = [row for _, _, row in pairs if row["status"] == "ok"]
        if valid:
            for row, adjusted in zip(valid, benjamini_hochberg([row["p_value"] for row in valid])):
                row["bh_adjusted_p_value"] = adjusted
        result["granger_predictability"] = [{"target": a, "lagged": b, **row} for a, b, row in pairs]
        result["cross_correlation"] = [
            {"lag": lag, "correlation": float(np.corrcoef(target[lag:], returns[:len(target)-lag, 1])[0, 1])}
            for lag in range(6)
        ]
    return result


def market_history(service):
    if hasattr(service, "view"):
        view = service.view()
        return view.frames, view.metadata
    return service.frames, {"mode": "synthetic", "as_of": service.as_of.isoformat(),
                            "source": "quantcore-synthetic-v1", "dataset_version": service.version, "currency": "USD"}
