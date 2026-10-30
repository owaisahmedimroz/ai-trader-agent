import numpy as np
import pandas as pd
import pytest

from trader_agent.expr import ExprError, check_names, evaluate_bool, names, parse


@pytest.fixture
def frame():
    return pd.DataFrame(
        {
            "rsi_14": [25.0, 50.0, 75.0, np.nan],
            "close": [1.0, 2.0, 3.0, 4.0],
            "ema_50": [2.0, 2.0, 2.0, 2.0],
            "m15_trend": ["up", "down", "up", "na"],
            "bullish": [True, False, True, False],
        }
    )


@pytest.mark.parametrize(
    "expr, expected",
    [
        ("rsi_14 < 30", [True, False, False, False]),
        ("20 < rsi_14 < 60", [True, True, False, False]),
        ("m15_trend == 'up'", [True, False, True, False]),
        ("m15_trend in ['up', 'flat']", [True, False, True, False]),
        ("m15_trend not in ['up']", [False, True, False, True]),
        ("bullish and close > ema_50", [False, False, True, False]),
        ("not bullish or rsi_14 > 70", [False, True, True, True]),
        ("abs(close - ema_50) <= 1", [True, True, True, False]),
        ("max(close, ema_50) > 2", [False, False, True, True]),
        ("close * 2 - 1 >= ema_50 + 1", [False, True, True, True]),
        ("true", [True, True, True, True]),
    ],
)
def test_conditions(frame, expr, expected):
    assert evaluate_bool(expr, frame).tolist() == expected


@pytest.mark.parametrize(
    "bad",
    ["__import__('os')", "close.real", "close[0]", "lambda x: x", "close ** 2", "m15_trend in m15_trend", "open(1)", ""],
)
def test_dangerous_or_unsupported_input_is_rejected(bad):
    with pytest.raises(ExprError):
        parse(bad)


def test_unknown_feature_suggests_the_right_name(frame):
    with pytest.raises(ExprError, match="rsi_14"):
        evaluate_bool("rsi < 30", frame)
    with pytest.raises(ExprError, match="did you mean"):
        check_names("rsi_41 < 30", frame.columns)


def test_names():
    assert names("rsi_14 < 30 and abs(close - ema_50) < 1 and m15_trend == 'up' and true") == {
        "rsi_14", "close", "ema_50", "m15_trend",
    }
