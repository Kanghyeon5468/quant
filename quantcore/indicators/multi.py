"""Resampled indicators and VWAP from validated provider minute aggregates."""
from functools import lru_cache

import numpy as np
import pandas as pd

from quantcore.backtesting.portfolio import load_minutes
from quantcore.indicators.technical import technical


@lru_cache(maxsize=2)
def archived_vwap(snapshot, snapshot_id):
    _, minutes, manifest = load_minutes(snapshot)
    if "vw" not in minutes:
        return {}, manifest.get("as_of")
    positive = minutes[minutes.v > 0].copy()
    positive["valid"] = np.isfinite(positive.vw) & (positive.vw > 0)
    positive["weighted"] = positive.vw * positive.v
    grouped = positive.groupby(["symbol", "session"]).agg(weighted=("weighted", "sum"), volume=("v", "sum"),
                                                           valid=("valid", "all"))
    return (grouped.weighted / grouped.volume).where(grouped.valid).dropna().to_dict(), manifest["as_of"]


def timeframe_frame(frame, timeframe):
    if timeframe == "daily":
        return frame
    period = "W-FRI" if timeframe == "weekly" else "M"
    grouping = frame.index.tz_localize(None).to_period(period)
    output = frame.assign(observed_at=frame.index).groupby(grouping).agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
        volume=("volume", "sum"), observed_at=("observed_at", "last"))
    return output.set_index("observed_at")


def report(frames, symbol, timeframe, vwap=None):
    frame = frames[symbol]
    clean = timeframe_frame(frame, timeframe)
    values = technical(clean)
    values["close"] = clean.close
    px = pd.DataFrame({name: history.close for name, history in frames.items()}).dropna()
    changes = px.diff()
    breadth = pd.DataFrame({"advancing": (changes > 0).sum(axis=1), "declining": (changes < 0).sum(axis=1),
                            "above_sma_50": (px > px.rolling(50).mean()).sum(axis=1)}).iloc[50:]
    benchmark = "SPY" if "SPY" in px else px.columns[0]
    if timeframe == "daily":
        values["relative_strength_20"] = px[symbol].pct_change(20) - px[benchmark].pct_change(20)
        if vwap is not None and "session" in frame:
            values["iex_session_vwap_raw"] = frame.session.map(lambda date: vwap.get((symbol, date)))
    return {"status": "ok", "timeframe": timeframe, "benchmark": benchmark, "universe_size": len(frames),
            "breadth": breadth.tail(63).reset_index(names="timestamp").to_dict("records"),
            "values": values.tail(252).reset_index(names="timestamp").to_dict("records"),
            "basis": "weekly/monthly last bucket can be in progress; breadth covers the loaded universe only",
            "vwap_basis": "volume-weighted provider minute VWAP; raw USD/share, verified IEX archive sessions"}
