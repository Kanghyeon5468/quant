"""Research-only allocation signals for the existing whole-account simulator."""
from functools import lru_cache

import numpy as np

from quantcore.backtesting.portfolio import load_minutes, replay

METHODS = ("cross_sectional_momentum", "pairs_rotation", "volatility_targeting", "etf_allocation")


def multipliers(histories, method):
    prices = {s: frame.signal_close for s, frame in histories.items()}
    if method == "cross_sectional_momentum":
        ranked = sorted(prices, key=lambda s: (-prices[s].iloc[-1]/prices[s].iloc[-21], s))
        return {s: float(s in ranked[:2]) for s in prices}
    if method == "etf_allocation":
        return {s: float(s == "SPY") for s in prices}
    if method == "volatility_targeting":
        return {s: float(min(1., .15/max(v.pct_change().tail(20).std()*np.sqrt(252), 1e-9)))
                for s, v in prices.items()}
    if method == "pairs_rotation":
        first, second = ("AAPL", "MSFT")
        if first not in prices or second not in prices:
            raise ValueError("pairs rotation requires AAPL and MSFT")
        spread = np.log(prices[first].iloc[-60:].to_numpy()/prices[second].iloc[-60:].to_numpy())
        sigma = spread[:-1].std(ddof=1)
        z = (spread[-1] - spread[:-1].mean()) / sigma if sigma > 0 else 0
        return {s: float((s == first and z < -1) or (s == second and z > 1)) for s in prices}
    raise ValueError("unknown basket strategy")


@lru_cache(maxsize=1)
def archive(path):
    return load_minutes(path)


@lru_cache(maxsize=16)
def compare(path, method, days):
    daily, minutes, manifest = archive(path)
    result = replay(daily, minutes, strategy="buy_hold", evaluation_sessions=days,
                    allocation=lambda histories: multipliers(histories, method))
    return {"status": "ok", "method": method, "source": manifest["source"],
            "as_of": manifest["as_of"], "evaluation_sessions": days, "metrics": result["metrics"],
            "audit": result["audit"], "curve": result["curve"],
            "basis": "long-only fixed cash slots; independent risk gate; IEX minute limit fills; paired rotation holds at most one leg"}
