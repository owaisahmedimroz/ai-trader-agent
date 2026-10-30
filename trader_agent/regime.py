"""Higher-timeframe trend, market regime and volatility state.

Higher-timeframe (M15/H1) values are attached to an M1 candle only once the HTF
candle is complete at the moment that M1 candle closes — no look-ahead.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

OHLC_AGG = {"open": "first", "high": "max", "low": "min", "close": "last"}


def resample_ohlc(m1: pd.DataFrame, rule: str) -> pd.DataFrame:
    htf = m1[["open", "high", "low", "close"]].resample(rule, label="left", closed="left").agg(OHLC_AGG)
    htf = htf.dropna()
    htf["close_time"] = htf.index + pd.Timedelta(rule)
    return htf


def join_completed(index: pd.DatetimeIndex, htf: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """For each M1 candle, values of the latest HTF candle complete when it closed."""
    left = pd.DataFrame({"decision_time": index + pd.Timedelta(minutes=1)})
    right = htf[["close_time", *columns]].sort_values("close_time")
    merged = pd.merge_asof(left, right, left_on="decision_time", right_on="close_time", direction="backward")
    merged.index = index
    return merged[columns]


def trend_label(close: pd.Series, ema_line: pd.Series, slope_bars: int = 3) -> pd.Series:
    """'up' / 'down' / 'flat' from price vs EMA and the EMA's slope; 'na' while warming up."""
    slope = ema_line - ema_line.shift(slope_bars)
    up = (close > ema_line) & (slope > 0)
    down = (close < ema_line) & (slope < 0)
    label = np.where(up, "up", np.where(down, "down", "flat"))
    label = np.where(ema_line.isna() | slope.isna(), "na", label)
    return pd.Series(label, index=close.index, dtype=object)


def regime_label(adx_values: pd.Series, trend_level: float = 25.0, range_level: float = 20.0) -> np.ndarray:
    return np.where(
        adx_values.isna(),
        "na",
        np.where(adx_values >= trend_level, "trend", np.where(adx_values < range_level, "range", "mixed")),
    )


def volatility_rank(atr_values: pd.Series, window: int = 1440) -> pd.Series:
    """Percentile (0..1) of the current ATR within the last `window` candles."""
    return atr_values.rolling(window, min_periods=window // 2).rank(pct=True)


def volatility_state(rank: pd.Series) -> np.ndarray:
    return np.where(rank.isna(), "na", np.where(rank > 0.8, "high", np.where(rank < 0.2, "low", "normal")))
