import pytest

from trader_agent.binary import break_even, expected_value, resolve
from trader_agent.stats import binomial_sf, max_streak, summarize, wilson_interval


def test_break_even():
    assert break_even(0.80) == pytest.approx(0.5556, abs=1e-4)
    assert break_even(0.77) == pytest.approx(0.5650, abs=1e-4)
    assert break_even(0.82) == pytest.approx(0.5495, abs=1e-4)


def test_expected_value():
    assert expected_value(0.60, 0.80) == pytest.approx(0.08)
    assert expected_value(0.50, 0.80) == pytest.approx(-0.10)


@pytest.mark.parametrize(
    "direction, entry, exit_, result",
    [("CALL", 1.0, 1.1, "WIN"), ("CALL", 1.1, 1.0, "LOSS"), ("PUT", 1.1, 1.0, "WIN"), ("PUT", 1.0, 1.0, "DRAW")],
)
def test_resolve(direction, entry, exit_, result):
    assert resolve(direction, entry, exit_) == result


def test_wilson_interval_known_value():
    low, high = wilson_interval(50, 100)
    assert low == pytest.approx(0.4038, abs=1e-4)
    assert high == pytest.approx(0.5962, abs=1e-4)


def test_binomial_tail():
    assert binomial_sf(8, 10, 0.5) == pytest.approx(56 / 1024)
    assert binomial_sf(0, 10, 0.5) == 1.0
    assert binomial_sf(11, 10, 0.5) == 0.0


def test_losing_streak_ignores_draws():
    assert max_streak(["LOSS", "DRAW", "LOSS", "WIN", "LOSS"]) == 2


def test_summary():
    s = summarize(["WIN"] * 6 + ["LOSS"] * 4 + ["DRAW"], 0.80)
    assert s["win_rate"] == pytest.approx(0.6)
    assert s["ev_per_trade"] == pytest.approx((6 * 0.8 - 4) / 11)
    assert s["ci_low"] < 0.6 < s["ci_high"]
    assert summarize([], 0.8)["win_rate"] is None
