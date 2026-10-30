"""Price levels traders watch: previous day, today so far, a session's range,
round numbers and confirmed swing points. Every value is causal."""

from __future__ import annotations

import numpy as np
import pandas as pd


def pip_size(pair: str) -> float:
    return 0.01 if pair.upper().endswith("JPY") else 0.0001


def day_levels(high: pd.Series, low: pd.Series, trading_day: np.ndarray) -> pd.DataFrame:
    """Previous trading day's high/low and today's running high/low."""
    day = pd.Series(trading_day, index=high.index)
    daily = pd.DataFrame({"high": high, "low": low, "day": day}).groupby("day").agg(
        high=("high", "max"), low=("low", "min")
    )
    previous = daily.shift(1)  # Monday's previous day is Friday (no weekend rows)
    return pd.DataFrame(
        {
            "pdh": day.map(previous["high"]),
            "pdl": day.map(previous["low"]),
            "day_high": high.groupby(day).cummax(),
            "day_low": low.groupby(day).cummin(),
        },
        index=high.index,
    )


def session_range(high: pd.Series, low: pd.Series, in_session: np.ndarray, trading_day: np.ndarray):
    """Running high/low of one session within each trading day, held after it ends."""
    day = pd.Series(trading_day, index=high.index)
    run_high = high.where(in_session).groupby(day).cummax().groupby(day).ffill()
    run_low = low.where(in_session).groupby(day).cummin().groupby(day).ffill()
    return run_high, run_low


def round_number_distance(price: pd.Series, pair: str, step_pips: int) -> pd.Series:
    """Distance in pips to the nearest round level (step 100 = "00" levels like 1.0800)."""
    in_pips = price / pip_size(pair)
    nearest = (in_pips / step_pips).round() * step_pips
    return (in_pips - nearest).abs()


def confirmed_swings(high: pd.Series, low: pd.Series, k: int = 2):
    """Latest swing high/low (fractal of 2k+1 bars), known only k bars after it formed."""
    window = 2 * k + 1
    is_high = high == high.rolling(window, center=True, min_periods=window).max()
    is_low = low == low.rolling(window, center=True, min_periods=window).min()
    last_high = high.where(is_high).shift(k).ffill()
    last_low = low.where(is_low).shift(k).ffill()
    return last_high, last_low
