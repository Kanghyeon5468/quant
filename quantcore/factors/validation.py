"""Forward diagnostics for a price-only factor using a lagged opening reference."""
import numpy as np
import pandas as pd

from quantcore.factors.engine import rank_ic


def price_factor_validation(frames):
    closes = pd.DataFrame({symbol: frame.get("signal_close", frame.close) for symbol, frame in frames.items()}).dropna()
    opens = pd.DataFrame({symbol: frame.open * frame.get("signal_close", frame.close) / frame.close
                          for symbol, frame in frames.items()}).reindex(closes.index)
    score = closes.pct_change(20)
    records = []
    for horizon in (1, 5, 20):
        future = opens.shift(-1-horizon)/opens.shift(-1)-1
        previous, rows = None, []
        # Sample disjoint forward holding windows at each horizon.
        for stamp in closes.index[20:-horizon-1:horizon]:
            values, realized = score.loc[stamp], future.loc[stamp]
            if values.isna().any() or realized.isna().any():
                continue
            groups = np.array_split(values.sort_values(ascending=False, kind="stable").index, min(5, len(values)))
            leaders = set(groups[0])
            rows.append({"timestamp": stamp, "rank_ic": rank_ic(values, realized),
                         "quantile_returns": [float(realized.loc[group].mean()) for group in groups],
                         "top_group_turnover": len(leaders - previous)/len(leaders) if previous is not None else None})
            previous = leaders
        ic = pd.Series([row["rank_ic"] for row in rows], dtype=float).dropna()
        records.append({"holding_sessions": horizon, "samples": len(rows), "mean_rank_ic": float(ic.mean()),
                        "icir": float(ic.mean()/ic.std()) if len(ic) > 1 and ic.std() > 0 else None,
                        "events": rows[-63:]})
    return {"status": "ok" if any(r["samples"] for r in records) else "unavailable", "horizons": records,
            "universe_size": len(frames), "basis": "20-session price momentum; enter at next observed open; gross price returns"}


def neutral_scores(rows, groups, size=True):
    """Residualize current raw composite scores against observed log cap and SIC groups."""
    frame = pd.DataFrame(rows)
    if len(frame) < 3 or "score" not in frame or "market_cap_estimate" not in frame:
        return {"status": "unavailable", "reason": "three or more observed company scores and caps required"}
    frame["classification"] = frame.symbol.map(groups)
    if groups and frame.classification.isna().any():
        return {"status": "unavailable", "reason": "missing point-in-time classification for part of the universe"}
    design = np.ones((len(frame), 1))
    if size:
        cap = frame.market_cap_estimate.to_numpy(float)
        if not np.isfinite(cap).all() or np.any(cap <= 0):
            return {"status": "unavailable", "reason": "positive point-in-time market caps required"}
        size_input = np.log(cap)
        design = np.column_stack([design, size_input - size_input.mean()])
    if groups:
        for key in sorted(frame.classification.unique())[1:]:
            design = np.column_stack([design, frame.classification == key])
    rank = np.linalg.matrix_rank(design)
    if len(frame) <= rank:
        return {"status": "unavailable", "reason": "not enough assets after controlling for the requested exposures"}
    fitted = design @ np.linalg.lstsq(design, frame.score.to_numpy(float), rcond=None)[0]
    frame["neutral_score"] = frame.score - fitted
    frame["removed_exposure"] = fitted
    subset = frame[["symbol", "classification", "market_cap_estimate", "score", "neutral_score", "removed_exposure"]]
    return {"status": "ok", "residual_degrees_of_freedom": int(len(frame) - rank), "rows": subset.to_dict("records")}
