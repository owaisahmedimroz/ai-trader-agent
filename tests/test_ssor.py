import sqlite3

import pandas as pd
import pytest

from trader_agent.ssor import SSoR, SignalRecord

T = pd.Timestamp("2026-11-10 14:00", tz="UTC")


def signal(db, minutes=0, mode="live"):
    at = T + pd.Timedelta(minutes=minutes)
    return db.record_signal(
        SignalRecord(mode, "EURUSD", "R07", 2, "CALL", at - pd.Timedelta(minutes=1), at, at + pd.Timedelta(seconds=10), 1, 0.8,
                     {"rsi_14": 28.5}, {"allowed": True}, ksor_commit="abc123")
    )


@pytest.fixture
def db():
    store = SSoR(":memory:")
    yield store
    store.close()


def test_signal_roundtrip_keeps_provenance(db):
    sid = signal(db)
    stored = db.get_signal(sid)
    assert stored["setup_id"] == "R07" and stored["setup_version"] == 2
    assert stored["ksor_commit"] == "abc123"
    assert stored["features"] == {"rsi_14": 28.5}
    assert stored["gate"] == {"allowed": True}


def test_append_only(db):
    signal(db)
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        db.conn.execute("UPDATE signals SET pair = 'GBPUSD'")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        db.conn.execute("DELETE FROM signals")


def test_broker_result_beats_feed_result(db):
    sid = signal(db)
    db.record_outcome(sid, "feed", "LOSS", T + pd.Timedelta(minutes=1), 1.1000, 1.0999)
    db.record_outcome(sid, "broker", "WIN", T + pd.Timedelta(minutes=2))
    assert db.best_outcome(sid)["result"] == "WIN"
    assert db.best_outcome(sid)["pnl_units"] == pytest.approx(0.8)


def test_day_summary_counts_human_actions(db):
    a, b, c = signal(db, 0), signal(db, 5), signal(db, 10)
    db.record_action(a, "TAKEN", T + pd.Timedelta(seconds=4))
    db.record_outcome(a, "broker", "LOSS", T + pd.Timedelta(minutes=1))
    db.record_action(b, "TAKEN", T + pd.Timedelta(minutes=5, seconds=25))  # 25 s late
    db.record_outcome(b, "feed", "WIN", T + pd.Timedelta(minutes=6))
    db.record_action(c, "SKIPPED", T + pd.Timedelta(minutes=10, seconds=3))
    db.record_outcome(c, "feed", "WIN", T + pd.Timedelta(minutes=11))
    s = db.day_summary(T - pd.Timedelta(hours=1), T + pd.Timedelta(hours=1))
    assert (s["signals"], s["taken"], s["skipped"], s["late_entries"]) == (3, 2, 1, 1)
    assert (s["taken_wins"], s["taken_losses"]) == (1, 1)
    assert s["taken_pnl_units"] == pytest.approx(-0.2)
    assert s["all_win_rate"] == pytest.approx(2 / 3)
    assert db.latest_action(a)["reaction_seconds"] == pytest.approx(4.0)


def test_unresolved_and_proposals(db):
    a, b = signal(db, 0), signal(db, 5)
    db.record_outcome(a, "feed", "WIN", T + pd.Timedelta(minutes=1))
    assert [s["id"] for s in db.unresolved_signals()] == [b]
    pid = db.propose_lesson("R07 fails in high volatility", [a, b], {"win_rate": 0.4}, "agent", T)
    assert [p["id"] for p in db.pending_proposals()] == [pid]
    db.decide_proposal(pid, "approved", "Ustad", T + pd.Timedelta(days=1))
    assert db.pending_proposals() == []


def test_decision_log(db):
    db.log_decision(T, "EURUSD", "R07", "blocked", ["news blackout: CPI"])
    assert db.recent_decisions(1)[0]["reasons"] == ["news blackout: CPI"]


def test_file_database_is_created(tmp_path):
    path = tmp_path / "nested" / "ssor.sqlite3"
    with SSoR(path) as db:
        signal(db)
    assert path.exists()
