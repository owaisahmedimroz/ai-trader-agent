import pandas as pd
import pytest

from trader_agent.gate import DayState, RiskGate
from trader_agent.ksor import risk_policy_from_dict
from trader_agent.news import NewsEvent

POLICY = {
    "version": 1,
    "status": "draft",
    "allowed_sessions": ["london_newyork"],
    "max_signals_per_day": 5,
    "max_losses_per_day": 3,
    "cooldown": {"after_consecutive_losses": 2, "minutes": 10},
    "min_minutes_between_signals": 2,
    "news_blackout": {"impact": ["high"], "minutes_before": 15, "minutes_after": 15},
    "max_feed_lag_seconds": 5,
    "min_payout": 0.75,
}
NOW = pd.Timestamp("2026-11-10 14:00", tz="UTC")  # 19:00 PKT, inside the overlap


@pytest.fixture
def gate(sessions):
    return RiskGate(risk_policy_from_dict(POLICY), sessions)


def check(gate, state=None, now=NOW, payout=0.80, lag=None):
    return gate.check(now=now, pair="EURUSD", state=state or DayState(), payout=payout, feed_lag_seconds=lag)


def test_clear_conditions_allow(gate):
    decision = check(gate)
    assert decision.allowed and decision.reasons == ()


@pytest.mark.parametrize(
    "now, reason",
    [
        (pd.Timestamp("2026-11-10 09:00", tz="UTC"), "outside allowed sessions"),
        (pd.Timestamp("2026-11-14 14:00", tz="UTC"), "market closed"),
    ],
)
def test_time_blocks(gate, now, reason):
    decision = check(gate, now=now)
    assert not decision.allowed and any(reason in r for r in decision.reasons)


def test_news_blackout(gate):
    gate.add_event(NewsEvent(NOW + pd.Timedelta(minutes=10), "USD", "high", "CPI"))
    decision = check(gate)
    assert not decision.allowed and "CPI" in decision.reasons[0]
    assert check(gate, now=NOW + pd.Timedelta(minutes=26)).allowed  # 16 min after the event
    gate.events = [NewsEvent(NOW, "JPY", "high", "BoJ")]
    assert check(gate).allowed  # JPY news does not affect EURUSD


def test_whole_day_news_rule_uses_the_pakistan_calendar_day(sessions):
    policy = risk_policy_from_dict({**POLICY, "allowed_sessions": [],
                                    "news_blackout": {"impact": ["high"], "whole_day": True, "day_timezone": "Asia/Karachi"}})
    cpi = NewsEvent(pd.Timestamp("2026-11-10 13:30", tz="UTC"), "USD", "high", "CPI")  # 18:30 PKT on 10 Nov
    gate = RiskGate(policy, sessions, [cpi])
    morning = pd.Timestamp("2026-11-10 03:00", tz="UTC")  # 08:00 PKT, hours before the release
    decision = check(gate, now=morning)
    assert not decision.allowed and "news day: CPI" in decision.reasons[0]
    assert not check(gate, now=pd.Timestamp("2026-11-10 18:30", tz="UTC")).allowed  # 23:30 PKT, same day
    assert check(gate, now=pd.Timestamp("2026-11-10 19:30", tz="UTC")).allowed  # 00:30 PKT on 11 Nov
    gate.events = [NewsEvent(cpi.time_utc, "JPY", "high", "BoJ")]
    assert check(gate, now=morning).allowed  # JPY news does not touch EURUSD


def test_policy_rejects_unknown_day_timezone():
    import pytest as _pytest

    from trader_agent.ksor import KsorError

    with _pytest.raises(KsorError, match="day_timezone"):
        risk_policy_from_dict({**POLICY, "news_blackout": {"whole_day": True, "day_timezone": "Mars/Base"}})


def test_daily_loss_limit_and_cooldown(gate):
    state = DayState()
    state.record_outcome("LOSS", NOW - pd.Timedelta(minutes=30))
    state.record_outcome("LOSS", NOW - pd.Timedelta(minutes=5))
    decision = check(gate, state)
    assert not decision.allowed and "cooldown" in decision.reasons[0]
    assert check(gate, state, now=NOW + pd.Timedelta(minutes=6)).allowed  # cooldown over
    state.record_outcome("LOSS", NOW)
    assert "daily loss limit" in check(gate, state, now=NOW + pd.Timedelta(hours=1)).reasons[0]


def test_win_resets_the_losing_streak(gate):
    state = DayState()
    state.record_outcome("LOSS", NOW - pd.Timedelta(minutes=3))
    state.record_outcome("WIN", NOW - pd.Timedelta(minutes=2))
    state.record_outcome("LOSS", NOW - pd.Timedelta(minutes=1))
    assert check(gate, state).allowed


def test_spacing_signal_limit_lag_payout_and_user_controls(gate):
    state = DayState()
    state.record_signal("EURUSD", NOW - pd.Timedelta(minutes=1))
    assert any("too soon" in r for r in check(gate, state).reasons)
    state.signals = 5
    assert any("daily signal limit" in r for r in check(gate, state, now=NOW + pd.Timedelta(minutes=5)).reasons)
    assert any("stale data" in r for r in check(gate, lag=12).reasons)
    assert any("payout" in r for r in check(gate, payout=0.70).reasons)
    assert any("/stop" in r for r in check(gate, DayState(stopped=True)).reasons)
    paused = DayState(paused_until=NOW + pd.Timedelta(minutes=5))
    assert any("/pause" in r for r in check(gate, paused).reasons)


def test_new_day_resets_counters_but_keeps_stop():
    state = DayState(stopped=True)
    state.roll(pd.Timestamp("2026-11-10").date())
    state.record_outcome("LOSS", NOW)
    state.roll(pd.Timestamp("2026-11-11").date())
    assert state.losses == 0 and state.stopped
