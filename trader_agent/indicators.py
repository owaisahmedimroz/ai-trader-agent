"""Technical indicators, written to match TradingView's built-ins.

TradingView seeds EMA/RMA with a simple average of the first `n` values, and
uses a population standard deviation for Bollinger Bands; we do the same so the
numbers agree with what the Ustad sees on his charts. Every function is causal:
the value at bar t only uses bars <= t.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _seeded_ewm(values: pd.Series, n: int, alpha: float) -> pd.Series:
    """Exponential average seeded with the mean of the first `n` valid values."""
    s = values.astype("float64")
    valid = np.flatnonzero(s.notna().to_numpy())
    if len(valid) < n:
        return pd.Series(np.nan, index=s.index)
    first = valid[0]
    seed_at = first + n - 1
    x = s.copy()
    x.iloc[:seed_at] = np.nan
    x.iloc[seed_at] = s.iloc[first : seed_at + 1].mean()
    return x.ewm(alpha=alpha, adjust=False).mean()


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.astype("float64").rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return _seeded_ewm(s, n, 2.0 / (n + 1))


def rma(s: pd.Series, n: int) -> pd.Series:
    """Wilder's moving average (TradingView `ta.rma`)."""
    return _seeded_ewm(s, n, 1.0 / n)


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.astype("float64").diff()
    avg_up = rma(delta.clip(lower=0), n)
    avg_down = rma((-delta).clip(lower=0), n)
    out = 100 - 100 / (1 + avg_up / avg_down)
    out = out.mask((avg_down == 0) & (avg_up > 0), 100.0)
    out = out.mask((avg_down == 0) & (avg_up == 0), 50.0)
    return out


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    ranges = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1)
    return ranges.max(axis=1)  # first bar: high - low


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    return rma(true_range(high, low, close), n)


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0):
    """Returns (middle, upper, lower, width) where width = (upper - lower) / middle."""
    mid = sma(close, n)
    sd = close.astype("float64").rolling(n, min_periods=n).std(ddof=0)
    upper, lower = mid + k * sd, mid - k * sd
    return mid, upper, lower, (upper - lower) / mid


def dmi(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14, adx_n: int = 14):
    """Returns (adx, plus_di, minus_di) like TradingView `ta.dmi`."""
    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=high.index)
    tr = true_range(high, low, close)
    plus_dm.iloc[0] = minus_dm.iloc[0] = tr.iloc[0] = np.nan  # no previous bar yet
    tr_avg = rma(tr, n)
    plus_di = 100 * rma(plus_dm, n) / tr_avg
    minus_di = 100 * rma(minus_dm, n) / tr_avg
    total = plus_di + minus_di
    dx = (plus_di - minus_di).abs() / total.where(total != 0, 1.0)
    return 100 * rma(dx, adx_n), plus_di, minus_di


def stochastic(high: pd.Series, low: pd.Series, close: pd.Series, k: int = 14, smooth_k: int = 3, d: int = 3):
    """Returns (%K, %D) — the common "14, 3, 3" stochastic."""
    lowest = low.rolling(k, min_periods=k).min()
    highest = high.rolling(k, min_periods=k).max()
    raw = 100 * (close - lowest) / (highest - lowest).replace(0, np.nan)
    k_line = sma(raw, smooth_k)
    return k_line, sma(k_line, d)
