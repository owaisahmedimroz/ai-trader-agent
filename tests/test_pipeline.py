from dataclasses import replace

import pandas as pd
import pytest

from conftest import synthetic_candles
from trader_agent.config import load_settings
from trader_agent.control import Control
from trader_agent.gate import RiskGate
from trader_agent.ksor import risk_policy_from_dict, setup_from_dict
from trader_agent.pipeline import Agent
from trader_agent.ssor import SSoR
from trader_agent.timeutil import SessionBook


class Collector:
    def __init__(self):
        self.signals = []

    def send_signal(self, signal, setup_name=None):
        self.signals.append(signal)

    def send_text(self, text):
        pass


POLICY = {
    "version": 1, "status": "draft", "allowed_sessions": ["london_newyork"],
    "max_signals_per_day": 4, "max_losses_per_day": 3,
    "cooldown": {"after_consecutive_losses": 2, "minutes": 10}, "min_minutes_between_signals": 2,
    "entry_window_seconds": 10,
}


def make_agent(repo_root, tmp_path, conditions=("bullish",)):
    settings = load_settings(root=repo_root)
    sessions = SessionBook.from_yaml(settings.sessions_path)
    policy = risk_policy_from_dict(POLICY, sessions.names())
    setup = setup_from_dict({
        "id": "T01", "name": "test", "version": 1, "status": "draft", "direction": "CALL",
        "pairs": ["EURUSD"], "sessions": ["london_newyork"], "conditions": list(conditions),
    })
    return Agent(
        settings=replace(settings, lookback_bars=2000),
        sessions=sessions,
        setups=[setup],
        policy=policy,
        gate=RiskGate(policy, sessions),
        ssor=SSoR(tmp_path / "ssor.sqlite3"),
        notifier=Collector(),
        mode="replay",
        control_path=tmp_path / "control.json",
        ksor_version="test",
    )


def replay(agent, candles, start, minutes):
    positions = range(candles.index.get_loc(start), candles.index.get_loc(start) + minutes)
    for pos in positions:
        agent.on_closed_candle("EURUSD", candles.iloc[max(0, pos - 1999) : pos + 1])


@pytest.fixture
def candles():
    return synthetic_candles(days=3, seed=2)


def test_replay_sends_spaced_signals_and_respects_daily_limit(repo_root, tmp_path, candles):
    agent = make_agent(repo_root, tmp_path)
    replay(agent, candles, pd.Timestamp("2026-03-04 13:30", tz="UTC"), 120)
    signals = agent.notifier.signals
    assert 1 <= len(signals) <= POLICY["max_signals_per_day"]
    times = [pd.Timestamp(s["signal_time"]) for s in signals]
    assert all(b - a >= pd.Timedelta(minutes=2) for a, b in zip(times, times[1:]))
    assert all(s["ksor_commit"] == "test" and s["mode"] == "replay" for s in signals)
    assert all(pd.Timestamp(s["entry_deadline"]) - pd.Timestamp(s["signal_time"]) == pd.Timedelta(seconds=10) for s in signals)
    blocked = [d for d in agent.ssor.recent_decisions(500) if d["decision"] == "blocked"]
    assert blocked, "gate decisions (incl. blocks) are logged"


def test_feed_outcomes_are_resolved_after_expiry(repo_root, tmp_path, candles):
    agent = make_agent(repo_root, tmp_path)
    replay(agent, candles, pd.Timestamp("2026-03-04 13:30", tz="UTC"), 60)
    first = agent.notifier.signals[0]
    outcome = agent.ssor.best_outcome(first["id"])
    assert outcome is not None and outcome["source"] == "feed"
    entry_bar = pd.Timestamp(first["signal_time"])
    assert outcome["entry_price"] == pytest.approx(candles.loc[entry_bar, "open"])
    assert outcome["exit_price"] == pytest.approx(candles.loc[entry_bar, "close"])


def test_stop_and_news_from_control_file_block_signals(repo_root, tmp_path, candles):
    agent = make_agent(repo_root, tmp_path)
    Control(stopped=True).save(tmp_path / "control.json")
    replay(agent, candles, pd.Timestamp("2026-03-04 13:30", tz="UTC"), 30)
    assert agent.notifier.signals == []
    reasons = " ".join(" ".join(d["reasons"]) for d in agent.ssor.recent_decisions(50))
    assert "/stop" in reasons


def test_nothing_outside_allowed_sessions(repo_root, tmp_path, candles):
    agent = make_agent(repo_root, tmp_path)
    replay(agent, candles, pd.Timestamp("2026-03-04 03:00", tz="UTC"), 60)  # Asia hours
    assert agent.notifier.signals == []


def test_live_mode_refuses_drafts(repo_root):
    settings = load_settings(root=repo_root)
    with pytest.raises(ValueError, match="approved"):
        Agent.from_settings(settings, Collector(), mode="live", include_drafts=True)
