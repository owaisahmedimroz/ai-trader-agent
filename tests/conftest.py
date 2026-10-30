from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trader_agent.timeutil import SessionBook

REPO_ROOT = Path(__file__).resolve().parent.parent


def synthetic_candles(start: str = "2026-03-02 00:00", days: int = 3, seed: int = 0, base: float = 1.0850) -> pd.DataFrame:
    """Random-walk M1 candles on weekdays only. Test data — it has no trading edge."""
    index = pd.date_range(start, periods=days * 1440, freq="1min", tz="UTC")
    index = index[index.day_of_week < 5]
    rng = np.random.default_rng(seed)
    steps = rng.normal(0, 0.00012, len(index))
    close = base + np.cumsum(steps)
    open_ = np.concatenate([[base], close[:-1]])
    wiggle = np.abs(rng.normal(0, 0.00008, (2, len(index))))
    high = np.maximum(open_, close) + wiggle[0]
    low = np.minimum(open_, close) - wiggle[1]
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=index)


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def sessions() -> SessionBook:
    return SessionBook.from_yaml(REPO_ROOT / "ksor" / "sessions.yaml")


@pytest.fixture
def candles() -> pd.DataFrame:
    return synthetic_candles()
