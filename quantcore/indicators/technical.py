"""Causal indicators; Ichimoku lagging display is excluded to avoid future values."""
import numpy as np
import pandas as pd


def wilder(series, period):
    result = pd.Series(np.nan, index=series.index, dtype=float)
    seed = []
    last = None
    for index, value in series.items():
        if not np.isfinite(value):
            continue
        if last is None:
            seed.append(value)
            if len(seed) == period:
                last = float(np.mean(seed))
                result.loc[index] = last
        else:
            last = (last*(period-1)+value)/period
            result.loc[index] = last
    return result


def technical(frame):
    if frame.empty:
        raise ValueError('price history required')
    if not frame.index.is_monotonic_increasing or frame.index.has_duplicates:
        raise ValueError('unique chronological prices required')
    c, h, lo, v = frame.close, frame.high, frame.low, frame.volume
    out = pd.DataFrame(index=frame.index)
    for n in (20, 50, 200):
        out[f'sma_{n}'] = c.rolling(n).mean()
    out['ema_20'] = c.ewm(span=20, adjust=False, min_periods=20).mean()
    weights = np.arange(1, 21)
    out['wma_20'] = c.rolling(20).apply(lambda x: np.dot(x, weights)/weights.sum(), raw=True)
    delta = c.diff()
    gain, loss = wilder(delta.clip(lower=0), 14), wilder(-delta.clip(upper=0), 14)
    out['rsi_14'] = 100-100/(1+gain/loss.replace(0, np.nan))
    out.loc[(loss == 0) & (gain > 0), 'rsi_14'] = 100.
    out.loc[(loss == 0) & (gain == 0), 'rsi_14'] = 50.
    out['macd'] = c.ewm(span=12, adjust=False).mean()-c.ewm(span=26, adjust=False).mean()
    out['macd_signal'] = out.macd.ewm(span=9, adjust=False).mean()
    out['macd_histogram'] = out.macd-out.macd_signal
    std = c.rolling(20).std(ddof=0)
    out['bollinger_upper'] = out.sma_20+2*std
    out['bollinger_lower'] = out.sma_20-2*std
    tr = pd.concat([h-lo, (h-c.shift()).abs(), (lo-c.shift()).abs()], axis=1).max(axis=1)
    out['atr_14'] = wilder(tr, 14)
    up, down = h.diff(), -lo.diff()
    plus = wilder(up.where((up > down) & (up > 0), 0.), 14)
    minus = wilder(down.where((down > up) & (down > 0), 0.), 14)
    out['plus_di'] = 100*plus/out.atr_14.replace(0, np.nan)
    out['minus_di'] = 100*minus/out.atr_14.replace(0, np.nan)
    dx = 100*(out.plus_di-out.minus_di).abs()/(out.plus_di+out.minus_di).replace(0, np.nan)
    out['adx_14'] = wilder(dx, 14)
    typical = (h+lo+c)/3
    # Daily bars cannot recover true intraday VWAP: explicitly label rolling bar proxy.
    out['vwap_proxy_20'] = (typical*v).rolling(20).sum()/v.rolling(20).sum().replace(0, np.nan)
    out['obv'] = (np.sign(c.diff().fillna(0))*v).cumsum()
    lowest, highest = lo.rolling(14).min(), h.rolling(14).max()
    out['stochastic_k'] = 100*(c-lowest)/(highest-lowest).replace(0, np.nan)
    out['stochastic_d'] = out.stochastic_k.rolling(3).mean()
    out['ichimoku_tenkan'] = (h.rolling(9).max()+lo.rolling(9).min())/2
    out['ichimoku_kijun'] = (h.rolling(26).max()+lo.rolling(26).min())/2
    out['ichimoku_span_a'] = ((out.ichimoku_tenkan+out.ichimoku_kijun)/2).shift(26)
    out['ichimoku_span_b'] = ((h.rolling(52).max()+lo.rolling(52).min())/2).shift(26)
    out['donchian_upper'] = h.rolling(20).max()
    out['donchian_lower'] = lo.rolling(20).min()
    out['keltner_upper'] = out.ema_20+2*out.atr_14
    out['keltner_lower'] = out.ema_20-2*out.atr_14
    out['roc_20'] = c.pct_change(20)*100
    out['volume_ratio_20'] = v/v.rolling(20).mean().replace(0, np.nan)
    out['volatility_20'] = c.pct_change().rolling(20).std()*np.sqrt(252)
    out['breakout_20'] = (c > h.rolling(20).max().shift()).astype(int)
    return out.replace([np.inf, -np.inf], np.nan)
