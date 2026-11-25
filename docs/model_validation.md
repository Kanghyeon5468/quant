# Model validation

Implemented model comparison: Ridge(alpha10) vs training-mean DummyRegressor. Input features: 1/5/20-bar price returns and 20-bar volatility. Target: next 5-business-day return. No binary accuracy is compared with the previous SPY project.

Walk-forward starts after 300 usable feature rows, evaluates blocks of 63 bars, with 5-bar embargo. Retain training rows only when their target timestamp is strictly earlier than first test timestamp. StandardScaler is inside the training pipeline and fitted separately per fold. No shuffled splitting, test-based tuning or global feature scaling. Output includes split boundaries, sample counts, OOS MSE and directional accuracy.

Test targets overlap and are not independent. No significance or profitable trading conclusion follows from directional accuracy. Basic dependent-data uncertainty uses 5-bar moving block bootstrap in the statistics module; BH correction is available for user-supplied p-values. No hypothesis family was selected and “passed” after looking at the demo results.

Data version binds the Parquet snapshot by SHA-256; code/config and dependency locks make the run repeatable. No persistent trained-model registry, MLflow, SHAP, deep models, hyperparameter search or production drift alarm is claimed. Generated calculation report is deterministic Python output; LLM is disabled.

## Actual-source API evaluation · 2026-11-25

The same Ridge/train-mean walk-forward engine now runs on actual Alpaca price returns in the analysis API. AAPL has354 available sessions and one evaluation fold with29 observations per model for a5-session target. Baseline MSE0.0004370703854/direction65.52%; Ridge0.0003719827829/68.97%. These are a small, overlapping-target sample with no significance/profitability claim, no tuning on the test set, and no paper order integration. Source IDs/version and metrics are recorded in actual_api_validation.json. A short rolling-only cache returns insufficient_history rather than a fake model result.
