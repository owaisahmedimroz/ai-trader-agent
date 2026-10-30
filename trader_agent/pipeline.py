"""The agent loop's core: what happens each time an M1 candle closes.

    candles -> features -> KSoR setups -> DSoR gate -> SSoR record -> notify human

Replay (scripts/replay.py) and the live loop (Phase 2) both call
`Agent.on_closed_candle`, so they behave identically. The AI "brain" (Phase 3)
will slot in after the gate as an extra confirm/veto step; it can never skip it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .binary import resolve
from .config import Settings
from .control import Control
from .features import build_features, feature_names
from .gate import DayState, RiskGate
from .ksor import RiskPolicy, Setup, ksor_commit, load_risk_policy, load_setups
from .rules_engine import candidates_at
from .ssor import SSoR, SignalRecord
from .timeutil import SessionBook

MODES = ("live", "shadow", "replay")


@dataclass
class Agent:
    settings: Settings
    sessions: SessionBook
    setups: list[Setup]
    policy: RiskPolicy
    gate: RiskGate
    ssor: SSoR
    notifier: object
    mode: str = "replay"
    control_path: Path | None = None
    ksor_version: str = "unknown"
    count_only_taken: bool = False  # live: only trades the human took count toward loss limits
    state: DayState = field(default_factory=DayState)
    _pending: list[dict] | None = field(default=None, repr=False)  # signals waiting for the feed result

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        notifier,
        mode: str = "replay",
        include_drafts: bool = False,
        db_path: Path | str | None = None,
        control_path: Path | str | None = None,
    ) -> "Agent":
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        if mode == "live" and include_drafts:
            raise ValueError("live mode only runs approved setups")
        sessions = SessionBook.from_yaml(settings.sessions_path)
        statuses = ("approved", "draft") if include_drafts else ("approved",)
        setups = load_setups(settings.setups_dir, statuses, feature_names(sessions), sessions.names())
        policy = load_risk_policy(settings.risk_policy_path, sessions.names())
        if mode == "live" and policy.status != "approved":
            raise ValueError("live mode needs an approved risk policy (ksor/risk_policy.yaml)")
        return cls(
            settings=settings,
            sessions=sessions,
            setups=setups,
            policy=policy,
            gate=RiskGate(policy, sessions),
            ssor=SSoR(db_path or settings.db_path),
            notifier=notifier,
            mode=mode,
            control_path=Path(control_path) if control_path else None,
            ksor_version=ksor_commit(settings.ksor_dir),
            count_only_taken=(mode == "live"),
        )

    # ---- state ------------------------------------------------------------------

    def control(self) -> Control:
        return Control.load(self.control_path) if self.control_path else Control()

    def payout_for(self, pair: str, control: Control | None = None) -> float:
        control = control or self.control()
        return control.payouts.get(pair.upper(), self.settings.payout_default)

    def rebuild_state(self, now: pd.Timestamp, control: Control) -> DayState:
        """DSoR state for `now`, rebuilt from SSoR records and the control file."""
        day = self.sessions.trading_day_of(now)
        start, end = self.sessions.trading_day_bounds(day)
        state = DayState(trading_day=day)
        outcomes = []
        for signal in self.ssor.signals_between(start, end, mode=self.mode):
            signal_time = pd.Timestamp(signal["signal_time"])
            if signal_time > now:
                continue
            state.record_signal(signal["pair"], signal_time)
            outcome = self.ssor.best_outcome(signal["id"])
            if outcome is None:
                continue
            if self.count_only_taken:
                action = self.ssor.latest_action(signal["id"])
                if action is None or action["action"] != "TAKEN":
                    continue
            outcomes.append((pd.Timestamp(outcome["at"]), outcome["result"]))
        for at, result in sorted(outcomes):
            if at <= now:
                state.record_outcome(result, at)
        state.stopped = control.stopped
        state.paused_until = control.paused_until_ts()
        self.state = state
        return state

    # ---- per candle ---------------------------------------------------------------

    def resolve_outcomes(self, pair: str, candles: pd.DataFrame) -> int:
        """Record the feed's result for signals whose expiry candle has closed."""
        if self._pending is None:
            self._pending = self.ssor.unresolved_signals(mode=self.mode)
        resolved, still_waiting = 0, []
        for signal in self._pending:
            entry_bar = pd.Timestamp(signal["signal_time"])
            exit_bar = entry_bar + pd.Timedelta(minutes=signal["expiry_minutes"] - 1)
            if signal["pair"] != pair.upper() or exit_bar > candles.index[-1]:
                still_waiting.append(signal)  # other pair, or still running
                continue
            if entry_bar not in candles.index or exit_bar not in candles.index:
                continue  # data gap: no feed result; the human's broker result still counts
            entry_price = float(candles.at[entry_bar, "open"])
            exit_price = float(candles.at[exit_bar, "close"])
            result = resolve(signal["direction"], entry_price, exit_price)
            self.ssor.record_outcome(signal["id"], "feed", result, exit_bar + pd.Timedelta(minutes=1), entry_price, exit_price)
            resolved += 1
        self._pending = still_waiting
        return resolved

    def _might_signal(self, now: pd.Timestamp) -> bool:
        if not self.sessions.market_open(now):
            return False
        allowed = self.policy.allowed_sessions
        return not allowed or any(self.sessions.contains(name, now) for name in allowed)

    def on_closed_candle(self, pair: str, candles: pd.DataFrame, feed_lag_seconds: float | None = None) -> list[int]:
        """Call once per closed M1 candle with the latest candles (oldest first). Returns new signal ids."""
        if candles.empty:
            return []
        pair = pair.upper()
        now = candles.index[-1] + pd.Timedelta(minutes=1)
        self.resolve_outcomes(pair, candles)
        if not self._might_signal(now):
            return []  # nothing can be sent now: skip the feature work
        features = build_features(candles, pair, self.sessions, self.settings.display_timezone)
        candidates = candidates_at(self.setups, features, self.sessions, pair)
        if not candidates:
            return []
        control = self.control()
        self.gate.events = control.events()
        payout = self.payout_for(pair, control)
        new_ids = []
        for candidate in candidates:
            state = self.rebuild_state(now, control)
            decision = self.gate.check(now=now, pair=pair, state=state, payout=payout, feed_lag_seconds=feed_lag_seconds)
            self.ssor.log_decision(now, pair, candidate.setup_id, "signal" if decision.allowed else "blocked", decision.reasons)
            if not decision.allowed:
                continue
            record = SignalRecord(
                mode=self.mode,
                pair=pair,
                setup_id=candidate.setup_id,
                setup_version=candidate.setup_version,
                direction=candidate.direction,
                bar_time=candidate.bar_time,
                signal_time=candidate.signal_time,
                entry_deadline=candidate.signal_time + pd.Timedelta(seconds=self.policy.entry_window_seconds),
                expiry_minutes=candidate.expiry_minutes,
                payout=payout,
                features=candidate.features,
                gate={"allowed": True, "policy_version": self.policy.version, "policy_status": self.policy.status},
                ksor_commit=self.ksor_version,
            )
            signal_id = self.ssor.record_signal(record, created_at=now if self.mode == "replay" else None)
            new_ids.append(signal_id)
            signal = self.ssor.get_signal(signal_id)
            if self._pending is not None:
                self._pending.append(signal)
            self.notifier.send_signal(signal, candidate.setup_name)
        return new_ids
