import pandas as pd
import pytest

from trader_agent.control import Control
from trader_agent.news import NewsEvent, blackout_mask, blackout_reason, load_events_csv, parse_manual


def test_manual_news_is_converted_from_pkt():
    event = parse_manual("18:30 USD high US CPI", pd.Timestamp("2026-11-10").date())
    assert event.time_utc == pd.Timestamp("2026-11-10 13:30", tz="UTC")
    assert (event.currency, event.impact, event.title) == ("USD", "high", "US CPI")
    assert parse_manual("19:00 eur", pd.Timestamp("2026-11-10").date()).impact == "high"
    with pytest.raises(ValueError):
        parse_manual("18:30 DOLLAR", pd.Timestamp("2026-11-10").date())


def test_blackout_window_edges():
    event = NewsEvent(pd.Timestamp("2026-11-10 13:30", tz="UTC"), "USD", "high", "CPI")
    at = pd.Timestamp("2026-11-10 13:15", tz="UTC")
    assert blackout_reason([event], "EURUSD", at, 15, 15)
    assert not blackout_reason([event], "EURUSD", at - pd.Timedelta(minutes=1), 15, 15)
    assert not blackout_reason([event], "EURUSD", at, 15, 15, impacts=("medium",))
    index = pd.date_range("2026-11-10 13:00", periods=60, freq="1min", tz="UTC")
    assert blackout_mask([event], "GBPUSD", index, 15, 15).sum() == 31


def test_events_csv(tmp_path):
    path = tmp_path / "news.csv"
    path.write_text("time_utc,currency,impact,title\n2026-11-10T13:30:00Z,usd,High,CPI\n", encoding="utf-8")
    events = load_events_csv(path)
    assert events[0].currency == "USD" and events[0].impact == "high"


def test_control_file_roundtrip(tmp_path):
    path = tmp_path / "control.json"
    control = Control.load(path)  # missing file -> defaults
    assert not control.stopped
    now = pd.Timestamp("2026-11-10 13:00", tz="UTC")
    control.pause(30, now)
    control.payouts["EURUSD"] = 0.82
    control.add_news(NewsEvent(now, "USD", "high", "CPI"))
    control.save(path)
    loaded = Control.load(path)
    assert loaded.paused_until_ts() == now + pd.Timedelta(minutes=30)
    assert loaded.payouts == {"EURUSD": 0.82}
    assert loaded.events()[0].title == "CPI"
    loaded.resume()
    assert loaded.paused_until is None and not loaded.stopped


def test_corrupt_control_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "control.json"
    path.write_text("{not json", encoding="utf-8")
    assert Control.load(path) == Control()
