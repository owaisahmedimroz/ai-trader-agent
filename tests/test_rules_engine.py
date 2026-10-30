import numpy as np
import pandas as pd

from trader_agent.ksor import setup_from_dict
from trader_agent.rules_engine import candidates_at, setup_mask


def frame(sessions, start="2026-11-10 13:00", periods=6):
    """Small hand-made feature frame inside the London–New York overlap (18:00 PKT)."""
    index = pd.date_range(start, periods=periods, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "rsi_14": [25.0, 40.0, 25.0, np.nan, 25.0, 25.0],
            "bullish": [True, True, True, True, False, True],
            "vol_state": ["normal", "normal", "high", "normal", "normal", "normal"],
            "m15_trend": ["up", "up", "up", "up", "up", "na"],
            "close": 1.1,
            "atr_14": 0.0002,
            "market_open": sessions.market_open_mask(index),
        },
        index=index,
    )


def make_setup(**changes):
    raw = {
        "id": "T01",
        "name": "test",
        "version": 2,
        "status": "draft",
        "direction": "PUT",
        "pairs": ["EURUSD"],
        "sessions": ["london_newyork"],
        "conditions": ["rsi_14 < 30", "bullish", "m15_trend == 'up'"],
        "invalidations": ["vol_state == 'high'"],
    }
    raw.update(changes)
    return setup_from_dict(raw)


def test_mask_combines_conditions_invalidations_and_warmup(sessions):
    features = frame(sessions)
    mask = setup_mask(make_setup(), features, sessions, "EURUSD")
    # row1 rsi 40, row2 invalidated, row3 NaN, row4 not bullish, row5 trend 'na' (warming up)
    assert mask.tolist() == [True, False, False, False, False, False]


def test_wrong_pair_never_fires(sessions):
    assert not setup_mask(make_setup(), frame(sessions), sessions, "GBPUSD").any()


def test_session_filter_uses_decision_time(sessions):
    # On 10 Nov 2026 New York opens at 13:00 UTC (08:00 EST), starting the overlap
    features = frame(sessions, start="2026-11-10 12:58", periods=6)
    mask = setup_mask(make_setup(conditions=["rsi_14 > 0"], invalidations=[]), features, sessions, "EURUSD")
    assert mask.tolist()[:2] == [False, True]  # 12:58 candle decides at 12:59 (outside), 12:59 candle at 13:00


def test_candidate_carries_provenance(sessions):
    features = frame(sessions).iloc[:1]
    found = candidates_at([make_setup()], features, sessions, "EURUSD")
    assert len(found) == 1
    c = found[0]
    assert (c.setup_id, c.setup_version, c.direction) == ("T01", 2, "PUT")
    assert c.signal_time == c.bar_time + pd.Timedelta(minutes=1)
    assert c.features["rsi_14"] == 25.0 and c.features["vol_state"] == "normal"
