"""Feature frame: everything a KSoR rule can refer to, one row per closed M1 candle.

Row t only uses information that existed when candle t closed, so the same frame
serves backtests, replays and the live loop (tests/test_features.py checks this).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import indicators as ind
from .levels import confirmed_swings, day_levels, pip_size, round_number_distance, session_range
from .regime import (
    join_completed,
    regime_label,
    resample_ohlc,
    trend_label,
    volatility_rank,
    volatility_state,
)
from .timeutil import DISPLAY_TZ, SessionBook

# name -> meaning. Rules may use these names (plus in_<session> flags).
BASE_FEATURES: dict[str, str] = {
    "open": "candle open",
    "high": "candle high",
    "low": "candle low",
    "close": "candle close",
    "prev_open": "previous candle open",
    "prev_high": "previous candle high",
    "prev_low": "previous candle low",
    "prev_close": "previous candle close",
    "body": "abs(close - open)",
    "candle_range": "high - low",
    "upper_wick": "high - max(open, close)",
    "lower_wick": "min(open, close) - low",
    "bullish": "close > open (hari candle)",
    "bearish": "close < open (laal candle)",
    "doji": "body <= 10% of range",
    "bullish_engulfing": "laal candle ke baad hari candle jo us ki body ko dhak le",
    "bearish_engulfing": "hari candle ke baad laal candle jo us ki body ko dhak le",
    "pin_bar_bull": "lambi neeche wali wick (>= 2x body aur >= 60% range)",
    "pin_bar_bear": "lambi upar wali wick (>= 2x body aur >= 60% range)",
    "ema_9": "EMA 9 (close)",
    "ema_21": "EMA 21 (close)",
    "ema_50": "EMA 50 (close)",
    "ema_200": "EMA 200 (close)",
    "rsi_14": "RSI 14",
    "atr_14": "ATR 14 (price units)",
    "bb_mid": "Bollinger middle (SMA 20)",
    "bb_up": "Bollinger upper (20, 2)",
    "bb_low": "Bollinger lower (20, 2)",
    "bb_width": "(bb_up - bb_low) / bb_mid",
    "adx_14": "ADX 14 (M1)",
    "plus_di": "+DI 14",
    "minus_di": "-DI 14",
    "stoch_k": "Stochastic %K (14, 3)",
    "stoch_d": "Stochastic %D (3)",
    "pdh": "previous trading day high",
    "pdl": "previous trading day low",
    "day_high": "today's high so far",
    "day_low": "today's low so far",
    "asia_high": "Tokyo session high (today)",
    "asia_low": "Tokyo session low (today)",
    "dist_round_00_pips": "pips to nearest 00 level (e.g. 1.0800)",
    "dist_round_50_pips": "pips to nearest 00/50 level",
    "last_swing_high": "latest confirmed swing high (5-bar fractal)",
    "last_swing_low": "latest confirmed swing low (5-bar fractal)",
    "m15_close": "last completed M15 close",
    "m15_ema_50": "EMA 50 on M15",
    "m15_trend": "'up' / 'down' / 'flat' (M15 price vs EMA 50 + slope)",
    "m15_adx": "ADX 14 on M15",
    "h1_trend": "'up' / 'down' / 'flat' (H1 price vs EMA 20 + slope)",
    "regime": "'trend' (M15 ADX >= 25) / 'range' (< 20) / 'mixed'",
    "atr_pct_rank": "ATR percentile vs last 24h (0..1)",
    "vol_state": "'low' / 'normal' / 'high' volatility",
    "market_open": "forex market open (Sun 17:00 – Fri 17:00 New York)",
    "hour_pkt": "hour in display timezone (default PKT)",
    "minute": "minute of the hour",
    "weekday": "0 = Monday ... 6 = Sunday (display timezone)",
    "pip_size": "0.0001 (0.01 for JPY pairs)",
}

STRING_FEATURES = ("m15_trend", "h1_trend", "regime", "vol_state")


def feature_names(sessions: SessionBook) -> list[str]:
    return list(BASE_FEATURES) + [f"in_{name}" for name in sessions.names()]


def validate_candles(candles: pd.DataFrame) -> None:
    missing = [c for c in ("open", "high", "low", "close") if c not in candles.columns]
    if missing:
        raise ValueError(f"candles are missing columns: {missing}")
    if not isinstance(candles.index, pd.DatetimeIndex) or candles.index.tz is None:
        raise ValueError("candles need a timezone-aware DatetimeIndex (UTC)")
    if not candles.index.is_monotonic_increasing or candles.index.has_duplicates:
        raise ValueError("candle timestamps must be sorted and unique")


def build_features(
    candles: pd.DataFrame, pair: str, sessions: SessionBook, display_tz: str = DISPLAY_TZ
) -> pd.DataFrame:
    validate_candles(candles)
    df = candles[["open", "high", "low", "close"]].astype("float64")
    df.index = df.index.tz_convert("UTC")
    idx = df.index
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]

    cols: dict[str, object] = {"open": o, "high": h, "low": l, "close": c}
    po, ph, pl, pc = o.shift(1), h.shift(1), l.shift(1), c.shift(1)
    cols.update(prev_open=po, prev_high=ph, prev_low=pl, prev_close=pc)

    body, rng = (c - o).abs(), h - l
    upper_wick, lower_wick = h - np.maximum(o, c), np.minimum(o, c) - l
    cols.update(
        body=body,
        candle_range=rng,
        upper_wick=upper_wick,
        lower_wick=lower_wick,
        bullish=c > o,
        bearish=c < o,
        doji=body <= 0.1 * rng,
        bullish_engulfing=(pc < po) & (c > o) & (o <= pc) & (c >= po),
        bearish_engulfing=(pc > po) & (c < o) & (o >= pc) & (c <= po),
        pin_bar_bull=(rng > 0) & (lower_wick >= 2 * body) & (lower_wick >= 0.6 * rng),
        pin_bar_bear=(rng > 0) & (upper_wick >= 2 * body) & (upper_wick >= 0.6 * rng),
    )

    for n in (9, 21, 50, 200):
        cols[f"ema_{n}"] = ind.ema(c, n)
    cols["rsi_14"] = ind.rsi(c, 14)
    atr14 = ind.atr(h, l, c, 14)
    cols["atr_14"] = atr14
    cols["bb_mid"], cols["bb_up"], cols["bb_low"], cols["bb_width"] = ind.bollinger(c, 20, 2.0)
    cols["adx_14"], cols["plus_di"], cols["minus_di"] = ind.dmi(h, l, c, 14, 14)
    cols["stoch_k"], cols["stoch_d"] = ind.stochastic(h, l, c, 14, 3, 3)

    trading_day = sessions.trading_day(idx)
    cols.update(day_levels(h, l, trading_day).to_dict("series"))
    if "tokyo" in sessions.sessions:
        cols["asia_high"], cols["asia_low"] = session_range(h, l, sessions.mask("tokyo", idx), trading_day)
    else:
        cols["asia_high"] = cols["asia_low"] = pd.Series(np.nan, index=idx)
    cols["dist_round_00_pips"] = round_number_distance(c, pair, 100)
    cols["dist_round_50_pips"] = round_number_distance(c, pair, 50)
    cols["last_swing_high"], cols["last_swing_low"] = confirmed_swings(h, l, k=2)

    m15 = resample_ohlc(df, "15min")
    m15["ema_50"] = ind.ema(m15["close"], 50)
    m15["trend"] = trend_label(m15["close"], m15["ema_50"])
    m15["adx"] = ind.dmi(m15["high"], m15["low"], m15["close"], 14, 14)[0]
    m15_joined = join_completed(idx, m15, ["close", "ema_50", "trend", "adx"])
    cols["m15_close"] = m15_joined["close"]
    cols["m15_ema_50"] = m15_joined["ema_50"]
    cols["m15_trend"] = m15_joined["trend"].fillna("na").astype(object)
    cols["m15_adx"] = m15_joined["adx"]

    h1 = resample_ohlc(df, "1h")
    h1["trend"] = trend_label(h1["close"], ind.ema(h1["close"], 20))
    cols["h1_trend"] = join_completed(idx, h1, ["trend"])["trend"].fillna("na").astype(object)

    cols["regime"] = pd.Series(regime_label(m15_joined["adx"]), index=idx, dtype=object)
    rank = volatility_rank(atr14)
    cols["atr_pct_rank"] = rank
    cols["vol_state"] = pd.Series(volatility_state(rank), index=idx, dtype=object)

    cols["market_open"] = sessions.market_open_mask(idx)
    for name in sessions.names():
        cols[f"in_{name}"] = sessions.mask(name, idx)
    local = idx.tz_convert(display_tz)
    cols["hour_pkt"] = np.asarray(local.hour)
    cols["minute"] = np.asarray(local.minute)
    cols["weekday"] = np.asarray(local.day_of_week)
    cols["pip_size"] = pip_size(pair)

    return pd.DataFrame(cols, index=idx)
