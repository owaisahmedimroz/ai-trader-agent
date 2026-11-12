"""DSoR — Data System of Record: current state + permission to act.

The risk gate decides, independently of any AI, whether a signal may be sent
right now. Its limits come from the approved risk policy (KSoR); its running
state (today's signals, losses, cooldowns, /stop and /pause) is rebuilt from
SSoR records. Nothing — including the AI — can override a blocked decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from .ksor import RiskPolicy
from .news import NewsEvent, blackout_reason, day_blackout_reason
from .timeutil import SessionBook, as_utc


@dataclass
class DayState:
    trading_day: date | None = None
    signals: int = 0
    losses: int = 0
    consecutive_losses: int = 0
    last_loss_at: pd.Timestamp | None = None
    last_signal_at: dict[str, pd.Timestamp] = field(default_factory=dict)
    paused_until: pd.Timestamp | None = None
    stopped: bool = False

    def roll(self, trading_day: date) -> None:
        """New forex day: reset daily counters (a manual /stop or /pause stays)."""
        if self.trading_day != trading_day:
            self.trading_day = trading_day
            self.signals = self.losses = self.consecutive_losses = 0
            self.last_loss_at = None
            self.last_signal_at = {}

    def record_signal(self, pair: str, at) -> None:
        self.signals += 1
        self.last_signal_at[pair.upper()] = as_utc(at)

    def record_outcome(self, result: str, at) -> None:
        if result == "LOSS":
            self.losses += 1
            self.consecutive_losses += 1
            self.last_loss_at = as_utc(at)
        elif result == "WIN":
            self.consecutive_losses = 0


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    reasons: tuple[str, ...] = ()


class RiskGate:
    def __init__(self, policy: RiskPolicy, sessions: SessionBook, events: list[NewsEvent] | None = None):
        self.policy = policy
        self.sessions = sessions
        self.events = list(events or [])

    def add_event(self, event: NewsEvent) -> None:
        self.events.append(event)

    def check(self, *, now, pair: str, state: DayState, payout: float, feed_lag_seconds: float | None = None) -> GateDecision:
        """`now` is the decision time (the moment the signal candle closed)."""
        now = as_utc(now)
        p = self.policy
        reasons = []
        if state.stopped:
            reasons.append("stopped by user (/stop)")
        if state.paused_until is not None and now < state.paused_until:
            reasons.append(f"paused until {state.paused_until:%H:%M} UTC (/pause)")
        if not self.sessions.market_open(now):
            reasons.append("market closed")
        if p.allowed_sessions and not any(self.sessions.contains(s, now) for s in p.allowed_sessions):
            reasons.append(f"outside allowed sessions {list(p.allowed_sessions)}")
        if p.news_whole_day:
            news = day_blackout_reason(self.events, pair, now, p.news_day_timezone, p.news_impacts)
        else:
            news = blackout_reason(self.events, pair, now, p.news_minutes_before, p.news_minutes_after, p.news_impacts)
        if news:
            reasons.append(news)
        if state.losses >= p.max_losses_per_day:
            reasons.append(f"daily loss limit reached ({state.losses}/{p.max_losses_per_day})")
        if state.signals >= p.max_signals_per_day:
            reasons.append(f"daily signal limit reached ({state.signals}/{p.max_signals_per_day})")
        if (
            state.consecutive_losses >= p.cooldown_after_losses
            and state.last_loss_at is not None
            and now < state.last_loss_at + pd.Timedelta(minutes=p.cooldown_minutes)
        ):
            until = state.last_loss_at + pd.Timedelta(minutes=p.cooldown_minutes)
            reasons.append(f"cooldown after {state.consecutive_losses} losses until {until:%H:%M} UTC")
        last = state.last_signal_at.get(pair.upper())
        if last is not None and now - last < pd.Timedelta(minutes=p.min_minutes_between_signals):
            reasons.append(f"too soon after previous {pair.upper()} signal ({p.min_minutes_between_signals} min gap)")
        if feed_lag_seconds is not None and feed_lag_seconds > p.max_feed_lag_seconds:
            reasons.append(f"stale data ({feed_lag_seconds:.1f}s old)")
        if payout < p.min_payout:
            reasons.append(f"payout {payout:.0%} below minimum {p.min_payout:.0%}")
        return GateDecision(allowed=not reasons, reasons=tuple(reasons))
