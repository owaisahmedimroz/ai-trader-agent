import numpy as np
import pandas as pd
import pytest

from trader_agent import indicators as ind


def series(values):
    return pd.Series(values, dtype="float64")


def test_ema_is_seeded_with_simple_average():
    s = series([1, 2, 3, 4, 5, 6])
    out = ind.ema(s, 3)
    assert out.iloc[:2].isna().all()
    assert out.iloc[2] == pytest.approx(2.0)  # mean(1, 2, 3)
    assert out.iloc[3] == pytest.approx(0.5 * 4 + 0.5 * 2.0)  # alpha = 2 / (3 + 1)


def test_rma_recursion():
    s = series([2, 4, 6, 8])
    out = ind.rma(s, 2)
    assert out.iloc[1] == pytest.approx(3.0)
    assert out.iloc[2] == pytest.approx((3.0 * 1 + 6) / 2)


def test_rsi_extremes():
    assert ind.rsi(series(range(1, 40))).iloc[-1] == pytest.approx(100.0)
    assert ind.rsi(series(range(40, 1, -1))).iloc[-1] == pytest.approx(0.0)
    assert ind.rsi(series([5.0] * 30)).iloc[-1] == pytest.approx(50.0)


def test_rsi_stays_in_range():
    rng = np.random.default_rng(1)
    out = ind.rsi(series(100 + np.cumsum(rng.normal(size=500)))).dropna()
    assert ((out >= 0) & (out <= 100)).all()


def test_atr_of_constant_range():
    high, low, close = series([2.0] * 30), series([1.0] * 30), series([1.5] * 30)
    assert ind.atr(high, low, close, 14).iloc[-1] == pytest.approx(1.0)


def test_bollinger_uses_population_std():
    close = series([1, 2, 3, 4])
    mid, up, low, width = ind.bollinger(close, 4, 2.0)
    std = np.std([1, 2, 3, 4])  # ddof = 0
    assert mid.iloc[-1] == pytest.approx(2.5)
    assert up.iloc[-1] == pytest.approx(2.5 + 2 * std)


def test_adx_is_high_in_a_clean_trend():
    n = 200
    close = series(np.linspace(1.0, 2.0, n))
    adx, plus_di, minus_di = ind.dmi(close + 0.01, close - 0.01, close)
    assert adx.iloc[-1] > 25
    assert plus_di.iloc[-1] > minus_di.iloc[-1]


def test_stochastic_bounds():
    rng = np.random.default_rng(2)
    close = series(100 + np.cumsum(rng.normal(size=300)))
    k, d = ind.stochastic(close + 0.5, close - 0.5, close)
    assert ((k.dropna() >= 0) & (k.dropna() <= 100)).all()
