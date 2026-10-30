import pandas as pd
import pytest

from trader_agent.notifier.actions import apply_callback, parse_pause, parse_payout
from trader_agent.notifier.messages import action_buttons, format_day_summary, format_signal, parse_callback
from trader_agent.notifier.telegram_sender import TelegramError, TelegramSender, keyboard
from trader_agent.ssor import SSoR, SignalRecord

T = pd.Timestamp("2026-11-10 13:47", tz="UTC")  # 18:47 PKT


@pytest.fixture
def db():
    store = SSoR(":memory:")
    store.record_signal(
        SignalRecord("live", "EURUSD", "R07", 2, "CALL", T - pd.Timedelta(minutes=1), T, T + pd.Timedelta(seconds=10), 1, 0.82,
                     {"m15_trend": "up", "regime": "range", "vol_state": "normal"})
    )
    yield store
    store.close()


def test_signal_message_has_what_the_human_needs(db):
    text = format_signal(db.get_signal(1), "Support bounce")
    assert "🟢 CALL — EUR/USD" in text
    assert "18:47:00 PKT" in text and "18:47:10 ke baad mat lagana" in text
    assert "R07 v2 — Support bounce" in text and "82%" in text and "#1" in text


def test_buttons_roundtrip():
    (taken, skipped), = action_buttons(7)
    assert parse_callback(taken[1]) == ("act", 7, "TAKEN")
    assert keyboard(action_buttons(7))["inline_keyboard"][0][1]["callback_data"] == "act:7:SKIPPED"
    for bad in ("act:7:MAYBE", "act:x:TAKEN", "zzz:7:WIN", ""):
        with pytest.raises(ValueError):
            parse_callback(bad)


def test_taken_then_loss_then_review_flow(db):
    text, buttons = apply_callback(db, "act:1:TAKEN", T + pd.Timedelta(seconds=5))
    assert "lagaya" in text and buttons[0][0][1] == "res:1:WIN"
    text, buttons = apply_callback(db, "res:1:LOSS", T + pd.Timedelta(minutes=1, seconds=10))
    assert buttons is not None and buttons[0][0][1] == "rev:1:normal"
    text, buttons = apply_callback(db, "rev:1:execution_error", T + pd.Timedelta(minutes=2))
    assert buttons is None
    assert db.best_outcome(1)["source"] == "broker" and db.best_outcome(1)["result"] == "LOSS"
    assert db.conn.execute("SELECT category FROM reviews").fetchone()[0] == "execution_error"


def test_late_entry_warning(db):
    text, _ = apply_callback(db, "act:1:TAKEN", T + pd.Timedelta(seconds=25))
    assert "der se" in text


def test_unknown_signal(db):
    text, buttons = apply_callback(db, "act:99:TAKEN", T)
    assert "nahi mila" in text and buttons is None


def test_command_parsers():
    assert parse_payout(["eurusd", "82"]) == ("EURUSD", 0.82)
    assert parse_payout(["EURUSD", "0.9"]) == ("EURUSD", 0.9)
    assert parse_pause(["30"]) == 30
    for bad in (["EURUSD"], ["EURUSD", "5"], ["EUR", "80"]):
        with pytest.raises(ValueError):
            parse_payout(bad)
    with pytest.raises(ValueError):
        parse_pause(["0"])


def test_day_summary_text(db):
    text = format_day_summary(db.day_summary(T - pd.Timedelta(hours=1), T + pd.Timedelta(hours=1)))
    assert "Signals: 1" in text


def test_sender_needs_a_token_and_chat():
    with pytest.raises(TelegramError):
        TelegramSender("", 1)
    with pytest.raises(TelegramError, match="CHAT_ID"):
        TelegramSender("123:abc").send_text("hi")
