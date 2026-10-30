"""Turns KSoR setups into signal candidates.

`setup_mask` evaluates a setup on a whole feature frame (backtests). The live
loop calls `candidates_at` on the same frame's latest row — one code path for
both, so a backtest measures exactly what the live agent would have done.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import reduce

import numpy as np
import pandas as pd

from .expr import evaluate_bool
from .ksor import Setup
from .timeutil import SessionBook

CONTEXT_FEATURES = ("close", "atr_14", "rsi_14", "m15_trend", "h1_trend", "regime", "vol_state", "hour_pkt")


@dataclass(frozen=True)
class Candidate:
    pair: str
    setup_id: str
    setup_version: int
    setup_name: str
    direction: str
    expiry_minutes: int
    bar_time: pd.Timestamp  # open time of the candle that produced the signal (UTC)
    signal_time: pd.Timestamp  # when that candle closed = decision time = next candle's open
    features: dict = field(default_factory=dict)


def setup_mask(setup: Setup, features: pd.DataFrame, sessions: SessionBook, pair: str) -> pd.Series:
    """True on every row where the setup fires for `pair`."""
    index = features.index
    if pair.upper() not in setup.pairs:
        return pd.Series(False, index=index)
    conditions = reduce(lambda a, b: a & b, (evaluate_bool(c, features) for c in setup.conditions))
    if setup.invalidations:
        invalid = reduce(lambda a, b: a | b, (evaluate_bool(c, features) for c in setup.invalidations))
    else:
        invalid = pd.Series(False, index=index)
    referenced = sorted(setup.referenced_features())
    complete = features[referenced].notna().all(axis=1) if referenced else pd.Series(True, index=index)
    for name in referenced:  # warming-up string features are 'na', not NaN
        if features[name].dtype == object:
            complete &= features[name] != "na"
    # Session and market hours are judged at the decision time (when the candle
    # closes and the trade would be placed), not at the candle's open.
    decision_times = index + pd.Timedelta(minutes=1)
    if setup.sessions:
        in_session = np.zeros(len(index), dtype=bool)
        for name in setup.sessions:
            in_session |= sessions.mask(name, decision_times)
    else:
        in_session = np.ones(len(index), dtype=bool)
    market_open = sessions.market_open_mask(decision_times)
    return conditions & ~invalid & complete & pd.Series(in_session & market_open, index=index)


def snapshot(row: pd.Series, setup: Setup) -> dict:
    """Features worth keeping with a signal (provenance + later analysis)."""
    keys = sorted(set(CONTEXT_FEATURES) | setup.referenced_features())
    out = {}
    for key in keys:
        if key not in row.index:
            continue
        value = row[key]
        if isinstance(value, (np.bool_, bool)):
            value = bool(value)
        elif isinstance(value, (np.integer,)):
            value = int(value)
        elif isinstance(value, (np.floating, float)):
            value = None if np.isnan(value) else round(float(value), 6)
        out[key] = value
    return out


def make_candidate(setup: Setup, features: pd.DataFrame, position: int, pair: str) -> Candidate:
    bar_time = features.index[position]
    return Candidate(
        pair=pair.upper(),
        setup_id=setup.id,
        setup_version=setup.version,
        setup_name=setup.name,
        direction=setup.direction,
        expiry_minutes=setup.expiry_minutes,
        bar_time=bar_time,
        signal_time=bar_time + pd.Timedelta(minutes=1),
        features=snapshot(features.iloc[position], setup),
    )


def candidates_at(setups: list[Setup], features: pd.DataFrame, sessions: SessionBook, pair: str) -> list[Candidate]:
    """Setups firing on the latest closed candle (live / replay)."""
    if features.empty:
        return []
    found = []
    for setup in setups:
        if setup_mask(setup, features, sessions, pair).iloc[-1]:
            found.append(make_candidate(setup, features, len(features) - 1, pair))
    return found
