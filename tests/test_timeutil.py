import pandas as pd

from trader_agent.timeutil import to_display


def pkt(ts: str) -> pd.Timestamp:
    return pd.Timestamp(ts, tz="Asia/Karachi").tz_convert("UTC")


def test_new_york_open_moves_with_us_daylight_saving(sessions):
    # 30 Oct 2026: UK already on winter time, US still on summer time -> NY opens 17:00 PKT
    assert sessions.contains("new_york", pkt("2026-10-30 17:00"))
    assert not sessions.contains("new_york", pkt("2026-10-30 16:59"))
    # 10 Nov 2026: US on winter time -> NY opens 18:00 PKT
    assert not sessions.contains("new_york", pkt("2026-11-10 17:30"))
    assert sessions.contains("new_york", pkt("2026-11-10 18:00"))


def test_london_session_in_pkt(sessions):
    assert sessions.contains("london", pkt("2026-11-10 13:00"))  # winter: 08:00 London
    assert not sessions.contains("london", pkt("2026-11-10 22:00"))
    assert sessions.contains("london", pkt("2027-06-10 12:00"))  # summer: 08:00 BST


def test_overlap_requires_both_sessions(sessions):
    assert sessions.contains("london_newyork", pkt("2026-11-10 19:00"))
    assert not sessions.contains("london_newyork", pkt("2026-11-10 14:00"))  # London only


def test_market_closed_on_weekend(sessions):
    assert not sessions.market_open(pd.Timestamp("2026-10-31 12:00", tz="UTC"))  # Saturday
    assert sessions.market_open(pd.Timestamp("2026-11-02 12:00", tz="UTC"))  # Monday
    # Friday 17:00 New York closes the week
    assert not sessions.market_open(pd.Timestamp("2026-11-06 17:00", tz="America/New_York"))
    assert sessions.market_open(pd.Timestamp("2026-11-06 16:59", tz="America/New_York"))


def test_trading_day_rolls_at_5pm_new_york(sessions):
    before = pd.Timestamp("2026-11-10 16:59", tz="America/New_York")
    after = pd.Timestamp("2026-11-10 17:00", tz="America/New_York")
    assert str(sessions.trading_day_of(before)) == "2026-11-10"
    assert str(sessions.trading_day_of(after)) == "2026-11-11"
    start, end = sessions.trading_day_bounds(sessions.trading_day_of(after))
    assert start == after.tz_convert("UTC")
    assert end - start == pd.Timedelta(hours=24)


def test_display_time_is_pkt():
    assert to_display(pd.Timestamp("2026-11-10 13:30", tz="UTC")) == "18:30:00"
