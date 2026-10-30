"""Backtest engine.

Runs KSoR setups over historical M1 candles using the same feature and rule
code as the live agent. Trade model (binary option, `entry: next_open`):

- signal on candle t (decided when t closes)
- entry = open of candle t+1, exit = close of candle t+expiry
- WIN / LOSS / DRAW by comparing exit with entry

M1 data cannot model the human's few seconds of delay; tick data can (later).
Prices come from the data provider, not Quotex, so results are an estimate —
the forward test on a demo account is the real exam.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ..binary import resolve
from ..features import build_features
from ..gate import DayState, RiskGate
from ..ksor import Setup
from ..rules_engine import setup_mask
from ..timeutil import DISPLAY_TZ, SessionBook

SESSION_PRIORITY = ("london_newyork", "london", "new_york", "tokyo", "sydney")


@dataclass
class BacktestConfig:
    payout: float = 0.80
    one_trade_at_a_time: bool = True
    use_gate: bool = False
    oos_from: pd.Timestamp | None = None
    display_tz: str = DISPLAY_TZ


@dataclass
class BacktestResult:
    pair: str
    setups: list[Setup]
    config: BacktestConfig
    trades: pd.DataFrame
    blocked: pd.DataFrame
    diagnostics: dict = field(default_factory=dict)


def _session_label(signal_time: pd.Timestamp, sessions: SessionBook) -> str:
    """Session at the decision time — the same moment the rules engine checks."""
    known = sessions.names()
    for name in [n for n in SESSION_PRIORITY if n in known] + known:
        if sessions.contains(name, signal_time):
            return name
    return "off_session"


def _trade(features: pd.DataFrame, setup: Setup, pos: int, pair: str, sessions: SessionBook, config: BacktestConfig):
    """Build one trade row, or return a skip reason."""
    index = features.index
    entry_pos, exit_pos = pos + 1, pos + setup.expiry_minutes
    if exit_pos >= len(index):
        return None, "end_of_data"
    if index[exit_pos] - index[pos] != pd.Timedelta(minutes=setup.expiry_minutes):
        return None, "data_gap"
    entry_price = float(features["open"].iat[entry_pos])
    exit_price = float(features["close"].iat[exit_pos])
    result = resolve(setup.direction, entry_price, exit_price)
    row = features.iloc[pos]
    signal_time = index[pos] + pd.Timedelta(minutes=1)
    local = signal_time.tz_convert(config.display_tz)
    pnl = config.payout if result == "WIN" else (-1.0 if result == "LOSS" else 0.0)
    trade = {
        "setup_id": setup.id,
        "setup_version": setup.version,
        "setup_status": setup.status,
        "direction": setup.direction,
        "pair": pair,
        "bar_time": index[pos],
        "signal_time": signal_time,
        "entry_time": index[entry_pos],
        "exit_time": index[exit_pos] + pd.Timedelta(minutes=1),
        "entry_price": entry_price,
        "exit_price": exit_price,
        "result": result,
        "pnl": pnl,
        "session": _session_label(signal_time, sessions),
        "hour_pkt": int(local.hour),
        "weekday": int(local.weekday()),
        "month": signal_time.strftime("%Y-%m"),
        "regime": row.get("regime"),
        "vol_state": row.get("vol_state"),
        "m15_trend": row.get("m15_trend"),
        "sample": "out" if config.oos_from is not None and signal_time >= config.oos_from else "in",
    }
    return trade, None


def run_backtest(
    candles: pd.DataFrame,
    pair: str,
    setups: list[Setup],
    sessions: SessionBook,
    config: BacktestConfig | None = None,
    gate: RiskGate | None = None,
) -> BacktestResult:
    config = config or BacktestConfig()
    pair = pair.upper()
    if config.use_gate and gate is None:
        raise ValueError("use_gate=True needs a RiskGate")
    features = build_features(candles, pair, sessions, config.display_tz)
    diagnostics: dict = {"bars": len(features), "raw_signals": {}, "skipped": {}}
    events = []
    for order, setup in enumerate(setups):
        positions = [int(p) for p in setup_mask(setup, features, sessions, pair).to_numpy().nonzero()[0]]
        diagnostics["raw_signals"][setup.key] = len(positions)
        events.extend((pos, order, setup) for pos in positions)
    events.sort(key=lambda e: (e[0], e[1]))

    trades, blocked = [], []
    skipped: dict[str, int] = {}

    def skip(reason: str) -> None:
        skipped[reason] = skipped.get(reason, 0) + 1

    if not config.use_gate:
        busy_until: dict[str, int] = {}
        for pos, _, setup in events:
            if config.one_trade_at_a_time and pos <= busy_until.get(setup.id, -1):
                skip("overlap")
                continue
            trade, reason = _trade(features, setup, pos, pair, sessions, config)
            if reason:
                skip(reason)
                continue
            trades.append(trade)
            busy_until[setup.id] = pos + setup.expiry_minutes
    else:
        state = DayState()
        pending: list[tuple[pd.Timestamp, str]] = []
        busy_until_pos = -1
        for pos, _, setup in events:
            now = features.index[pos] + pd.Timedelta(minutes=1)
            pending.sort(key=lambda item: item[0])
            while pending and pending[0][0] <= now:
                exit_time, result = pending.pop(0)
                state.roll(sessions.trading_day_of(exit_time))
                state.record_outcome(result, exit_time)
            state.roll(sessions.trading_day_of(now))
            if pos <= busy_until_pos:
                skip("overlap")
                continue
            decision = gate.check(now=now, pair=pair, state=state, payout=config.payout)
            if not decision.allowed:
                blocked.append({"setup_id": setup.id, "signal_time": now, "reasons": "; ".join(decision.reasons)})
                continue
            trade, reason = _trade(features, setup, pos, pair, sessions, config)
            if reason:
                skip(reason)
                continue
            trades.append(trade)
            state.record_signal(pair, now)
            pending.append((trade["exit_time"], trade["result"]))
            busy_until_pos = pos + setup.expiry_minutes

    diagnostics["skipped"] = skipped
    diagnostics["blocked"] = len(blocked)
    if len(features):
        diagnostics["first_bar"], diagnostics["last_bar"] = str(features.index[0]), str(features.index[-1])
    return BacktestResult(
        pair=pair,
        setups=setups,
        config=config,
        trades=pd.DataFrame(trades),
        blocked=pd.DataFrame(blocked),
        diagnostics=diagnostics,
    )
