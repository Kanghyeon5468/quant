"""Purged ML research with nested chronological tuning and OOS diagnostics."""
import hashlib
import json

import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import ElasticNet, Lasso, LinearRegression, Ridge
from sklearn.metrics import mean_squared_error
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

FEATURES = ("return_1", "return_5", "return_20", "volatility_20")
HORIZON = 5
EMBARGO = 5
VERSION = "research-returns-v1"


def estimators():
    return {
        "baseline": [DummyRegressor(strategy="mean")],
        "linear": [make_pipeline(StandardScaler(), LinearRegression())],
        "ridge": [make_pipeline(StandardScaler(), Ridge(alpha=x)) for x in (1., 10.)],
        "lasso": [make_pipeline(StandardScaler(), Lasso(alpha=x, max_iter=2000)) for x in (.0001, .001)],
        "elastic_net": [make_pipeline(StandardScaler(), ElasticNet(alpha=.0005, l1_ratio=x)) for x in (.2, .8)],
        "random_forest": [RandomForestRegressor(n_estimators=35, max_depth=x, random_state=42, n_jobs=1) for x in (2, 4)],
        "gradient_boosting": [HistGradientBoostingRegressor(max_iter=55, max_leaf_nodes=x, random_state=42) for x in (5, 10)],
        "mlp": [make_pipeline(StandardScaler(), MLPRegressor(hidden_layer_sizes=(8,), solver="lbfgs", alpha=.5,
                                                           max_iter=400, random_state=42))],
    }


def extended_validation(close):
    close = close.astype(float).dropna()
    frame = pd.DataFrame({f"return_{days}": close.pct_change(days) for days in (1, 5, 20)})
    frame["volatility_20"] = frame.return_1.rolling(20).std()
    frame["target"] = close.shift(-HORIZON)/close - 1
    frame["target_at"] = pd.Series(close.index, index=close.index).shift(-HORIZON)
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
    if len(frame) < 210:
        return {"status": "unavailable", "reason": "requires 210 usable observations after features and labels"}
    candidates, rows, folds = estimators(), [], []
    for start in range(160, len(frame), 50):
        test = frame.iloc[start:start+50]
        if len(test) < 20:
            continue
        train = frame.iloc[:start-EMBARGO]
        train = train[train.target_at < test.index[0]]
        validation = train.iloc[-35:]
        inner = train.iloc[:-35-EMBARGO]
        inner = inner[inner.target_at < validation.index[0]]
        x, y = train[list(FEATURES)], train.target
        test_x, actual = test[list(FEATURES)], test.target
        folds.append({"train_last_target": str(train.target_at.max()), "test_start": str(test.index[0]),
                      "test_end": str(test.index[-1]), "samples": len(test),
                      "feature_shift_train_std": {name: float(value) for name, value in (
                          (test_x.mean() - x.mean()) / x.std().replace(0, np.nan)).dropna().items()}})
        for name, options in candidates.items():
            chosen = min(
                enumerate(options),
                key=lambda item: mean_squared_error(validation.target, item[1].fit(
                    inner[list(FEATURES)], inner.target).predict(validation[list(FEATURES)])),
            )[0] if len(options) > 1 else 0
            model = options[chosen].fit(x, y)
            prediction = model.predict(test_x)
            row = {"model": name, "fold": len(folds), "parameters_index": chosen, "samples": len(test),
                   "mse": float(mean_squared_error(actual, prediction)),
                   "direction_accuracy": float((np.sign(prediction) == np.sign(actual)).mean())}
            if name == "ridge":
                scaler, regression = model.steps[0][1], model.steps[1][1]
                # Exact interventional attributions for a linear model and training-mean background.
                shap = scaler.transform(test_x)*regression.coef_
                if not np.allclose(shap.sum(axis=1)+regression.intercept_, prediction, rtol=1e-10, atol=1e-12):
                    raise ArithmeticError("linear attribution does not sum to prediction")
                row["mean_abs_linear_shap"] = dict(zip(FEATURES, np.abs(shap).mean(axis=0).tolist()))
            rows.append(row)
    if not folds:
        return {"status": "unavailable", "reason": "requires a completed out-of-sample window"}
    manifest = {"version": VERSION, "features": FEATURES, "horizon": HORIZON, "embargo": EMBARGO,
                "models": list(candidates), "start": str(frame.index[0]), "end": str(frame.index[-1]),
                "input_sha256": hashlib.sha256(pd.util.hash_pandas_object(close).to_numpy().tobytes()).hexdigest()}
    return {"status": "ok", "experiment": hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
            "manifest": manifest, "folds": folds, "models": rows,
            "basis": "nested chronological tuning; median-free features; overlapping forward targets; not a trading signal"}
