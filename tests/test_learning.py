import json
import urllib.error

import pandas as pd
import pytest

from conftest import synthetic_candles
from helpers import Recorder, make_agent
from trader_agent.calendar_feed import CalendarError, fetch_calendar, parse_ff_week
from trader_agent.control import Control
from trader_agent.learning import check_drift, setup_health, weekly_report
from trader_agent.notifier.actions import apply_callback
from trader_agent.ssor import SignalRecord

T0 = pd.Timestamp("2026-11-02 14:00", tz="UTC")


def add_results(ssor, setup_id, results, mode="live", brain=None):
    for i, result in enumerate(results):
        at = T0 + pd.Timedelta(minutes=3 * i)
        sid = ssor.record_signal(SignalRecord(mode, "EURUSD", setup_id, 1, "CALL", at, at, at, 1, 0.8, {}, brain=brain))
        ssor.record_outcome(sid, "feed", result, at + pd.Timedelta(minutes=1))


@pytest.mark.parametrize(
    "results, status",
    [
        (["WIN"] * 10, "WARMUP"),
        (["WIN"] * 20 + ["LOSS"] * 30, "DRIFT"),  # 40%, range top < 55.6%
        (["WIN"] * 26 + ["LOSS"] * 24, "WATCH"),  # 52%: below break-even but not proven
        (["WIN"] * 35 + ["LOSS"] * 15, "OK"),
    ],
)
def test_setup_health(repo_root, tmp_path, results, status):
    agent = make_agent(repo_root, tmp_path)
    add_results(agent.ssor, "T01", results)
    assert setup_health(agent.ssor, "T01", 0.8).status == status


def test_drift_pauses_setup_and_gate_respects_it(repo_root, tmp_path):
    recorder = Recorder()
    agent = make_agent(repo_root, tmp_path, notifier=recorder)
    add_results(agent.ssor, "T01", ["WIN"] * 15 + ["LOSS"] * 35)
    paused = check_drift(agent, recorder)
    assert [h.setup_id for h in paused] == ["T01"]
    assert "T01" in Control.load(agent.control_path).paused_setups
    assert "khud ruk gaya" in recorder.joined()
    assert check_drift(agent, recorder) == []  # already paused: no repeat alert

    candles = synthetic_candles(days=3, seed=2)
    first = candles.index.get_loc(pd.Timestamp("2026-03-04 13:30", tz="UTC"))
    for pos in range(first, first + 20):
        agent.on_closed_candle("EURUSD", candles.iloc[max(0, pos - 1999): pos + 1])
    assert recorder.signals == []
    reasons = " ".join(" ".join(d["reasons"]) for d in agent.ssor.recent_decisions(50))
    assert "setup paused" in reasons


def test_weekly_report_sections(repo_root, tmp_path):
    agent = make_agent(repo_root, tmp_path)
    add_results(agent.ssor, "T01", ["WIN", "LOSS", "WIN"], brain={"decision": "CONFIRM", "confidence": "high"})
    add_results(agent.ssor, "T01", ["LOSS", "LOSS"], mode="shadow", brain={"decision": "VETO", "confidence": "low"})
    agent.ssor.propose_lesson("T01 Friday ko band", [1, 2, 3], {}, "agent", T0)
    text = weekly_report(agent.ssor, T0 - pd.Timedelta(days=1), T0 + pd.Timedelta(days=1), 0.8, ["T01"])
    for heading in ("## Setups", "## AI ki value", "## Discipline", "## Loss reviews", "## AI calibration", "## Sabaq ki tajaweez"):
        assert heading in text
    assert "AI ne CONFIRM kiye: 67%" in text and "AI ne VETO kiye (bheje nahi gaye): 0%" in text
    assert "T01 Friday ko band" in text


def test_proposal_buttons_record_the_owner_decision(repo_root, tmp_path):
    agent = make_agent(repo_root, tmp_path)
    pid = agent.ssor.propose_lesson("pattern", [1], {}, "agent", T0)
    text, buttons = apply_callback(agent.ssor, f"prop:{pid}:approved", T0)
    assert "approve" in text and buttons is None
    assert agent.ssor.pending_proposals() == []
    again, _ = apply_callback(agent.ssor, f"prop:{pid}:rejected", T0)
    assert "pehle hi" in again


SAMPLE = [
    {"title": "CPI m/m", "country": "USD", "date": "2026-11-10T08:30:00-05:00", "impact": "High", "forecast": "0.3%", "previous": "0.2%"},
    {"title": "Bank Holiday", "country": "JPY", "date": "2026-11-10T00:00:00+09:00", "impact": "Holiday"},
    {"title": "ZEW", "country": "EUR", "date": "2026-11-10T05:00:00", "impact": "Medium"},
]


def test_parse_forex_factory_week():
    events = parse_ff_week(SAMPLE)
    assert [(e.currency, e.impact) for e in events] == [("EUR", "medium"), ("USD", "high")]
    usd = next(e for e in events if e.currency == "USD")
    assert usd.time_utc == pd.Timestamp("2026-11-10 13:30", tz="UTC")
    eur = next(e for e in events if e.currency == "EUR")
    assert eur.time_utc == pd.Timestamp("2026-11-10 10:00", tz="UTC")  # naive time = New York


def test_calendar_cache_and_offline_fallback(tmp_path, monkeypatch):
    cache = tmp_path / "calendar.json"

    def offline(*args, **kwargs):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr("urllib.request.urlopen", offline)
    with pytest.raises(CalendarError):
        fetch_calendar("https://example.invalid/feed.json", cache)
    cache.write_text(json.dumps(SAMPLE), encoding="utf-8")
    assert len(fetch_calendar("https://example.invalid/feed.json", cache)) == 2  # fresh cache, no download
    assert len(fetch_calendar("https://example.invalid/feed.json", cache, max_age_hours=0)) == 2  # stale cache fallback
