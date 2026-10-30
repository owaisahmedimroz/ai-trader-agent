import numpy as np
import pandas as pd
import pytest

from conftest import synthetic_candles
from trader_agent.features import build_features, feature_names, validate_candles


def test_all_documented_features_exist(candles, sessions):
    features = build_features(candles, "EURUSD", sessions)
    assert set(feature_names(sessions)) == set(features.columns)
    assert len(features) == len(candles)


@pytest.mark.parametrize("cut", [1500, 2222, 3333, 4100])
def test_no_look_ahead(cut, sessions):
    """Row t must not change when later candles are added (the core backtest-honesty rule)."""
    candles = synthetic_candles(days=4, seed=5)
    full = build_features(candles, "EURUSD", sessions)
    partial = build_features(candles.iloc[: cut + 1], "EURUSD", sessions)
    row_full, row_partial = full.iloc[cut], partial.iloc[-1]
    for column in full.columns:
        a, b = row_full[column], row_partial[column]
        if isinstance(a, (float, np.floating)) and np.isnan(a):
            assert np.isnan(b), column
        elif isinstance(a, (float, np.floating)):
            assert b == pytest.approx(a, rel=1e-9, abs=1e-12), column
        else:
            assert a == b, column


@pytest.mark.parametrize("seed", [8, 21, 34])
def test_live_window_matches_full_history(seed, sessions, repo_root):
    """The live loop only sees the last `lookback_bars` candles; its latest row must match full history."""
    from trader_agent.config import load_settings

    lookback = load_settings(root=repo_root).lookback_bars
    candles = synthetic_candles(days=8, seed=seed)
    full = build_features(candles, "EURUSD", sessions)
    window = build_features(candles.tail(lookback), "EURUSD", sessions)
    numeric = ("rsi_14", "atr_14", "ema_50", "ema_200", "pdh", "pdl", "m15_ema_50", "m15_adx", "atr_pct_rank")
    for column in numeric:
        assert window[column].iloc[-1] == pytest.approx(full[column].iloc[-1], rel=1e-4), column
    # trend labels may only differ on a knife-edge; require (near) full agreement on the last day
    last_day = slice(-1440, None)
    for column in ("m15_trend", "h1_trend", "regime", "vol_state"):
        agreement = (window[column].iloc[last_day].to_numpy() == full[column].iloc[last_day].to_numpy()).mean()
        assert agreement >= 0.99, (column, agreement)


def test_htf_trend_uses_only_completed_candles(sessions):
    candles = synthetic_candles(days=3, seed=9)
    features = build_features(candles, "EURUSD", sessions)
    # m15_close at 10:07 must be the close of the 09:45–09:59 candle (complete at 10:00)
    day = candles.index[1500].normalize()
    at = day + pd.Timedelta(hours=10, minutes=7)
    expected = candles.loc[day + pd.Timedelta(hours=9, minutes=59), "close"]
    assert features.loc[at, "m15_close"] == pytest.approx(expected)
    # at 10:14 the 10:00 candle closes -> m15_close is its close
    at2 = day + pd.Timedelta(hours=10, minutes=14)
    assert features.loc[at2, "m15_close"] == pytest.approx(candles.loc[at2, "close"])


def test_previous_day_levels(sessions):
    candles = synthetic_candles(days=3, seed=10)
    features = build_features(candles, "EURUSD", sessions)
    days = sessions.trading_day(candles.index)
    first_day, second_day = sorted(set(days))[1:3]
    expected_high = candles["high"][days == first_day].max()
    row = features[days == second_day].iloc[0]
    assert row["pdh"] == pytest.approx(expected_high)


def test_round_numbers_and_pip_size(sessions):
    candles = synthetic_candles(days=1, seed=1, base=150.00)
    features = build_features(candles, "USDJPY", sessions)
    assert features["pip_size"].iloc[0] == 0.01
    assert (features["dist_round_00_pips"] <= 50).all()


def test_rejects_naive_timestamps():
    frame = pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0]}, index=pd.DatetimeIndex(["2026-01-05"]))
    with pytest.raises(ValueError):
        validate_candles(frame)
