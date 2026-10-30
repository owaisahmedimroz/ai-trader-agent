import pandas as pd

from conftest import synthetic_candles
from helpers import Clock, FakeFeed, Recorder, make_agent
from trader_agent.live import LiveRunner, supports_forming
from trader_agent.feeds.base import Feed


def always_bullish(row):
    row["close"] = row["open"] + 0.0003
    row["high"] = row[["high", "close"]].max(axis=1)
    return row


def runner_for(agent, candles, start, forming=None, fail_times=0, **kwargs):
    clock = Clock(start)
    feed = FakeFeed(candles, clock, forming=forming, fail_times=fail_times)
    runner = LiveRunner([agent], feed, agent.notifier, now=clock, sleep=clock.sleep, **kwargs)
    return runner, clock


def test_session_start_briefing_signals_heartbeat_and_result_prompts(repo_root, tmp_path):
    candles = synthetic_candles(days=3, seed=2)
    recorder = Recorder()
    agent = make_agent(repo_root, tmp_path, notifier=recorder)
    # the human takes every signal 5 seconds after it arrives
    recorder.on_signal = lambda s: agent.ssor.record_action(s["id"], "TAKEN", pd.Timestamp(s["signal_time"]) + pd.Timedelta(seconds=5))
    runner, _ = runner_for(agent, candles, "2026-03-04 12:55:00", briefer=lambda facts: "AI commentary")
    runner.run(max_ticks=20)
    text = recorder.joined()
    assert "Agent online" in text
    assert "Session briefing" in text and "AI commentary" in text  # session started at 13:00 UTC
    assert "Zinda hun" in text
    assert recorder.signals, "the always-on test setup should signal inside the session"
    prompts = [b for t, b in recorder.texts if "kya nateeja aaya" in t]
    assert prompts and prompts[0][0][0][1].startswith("res:")
    first = pd.Timestamp(recorder.signals[0]["signal_time"])
    assert first >= pd.Timestamp("2026-03-04 13:00", tz="UTC")  # nothing before the overlap


def test_heads_up_then_go_or_cancel(repo_root, tmp_path):
    candles = synthetic_candles(days=3, seed=2)
    recorder = Recorder()
    agent = make_agent(repo_root, tmp_path, notifier=recorder)
    runner, _ = runner_for(agent, candles, "2026-03-04 13:10:00", forming=always_bullish)
    runner.run(max_ticks=30)
    heads_ups = [t for t, _ in recorder.texts if t.startswith("⚡ TAYYAR")]
    cancels = [t for t, _ in recorder.texts if t.startswith("❌ CANCEL")]
    assert heads_ups and cancels, "forming candle is always bullish, the real one often is not"
    assert len(heads_ups) == len(cancels) + len(recorder.signals)
    assert runner.heads_ups == {}  # every heads-up was answered


def test_session_end_summary_drift_check_and_review(repo_root, tmp_path):
    candles = synthetic_candles(days=3, seed=2)
    recorder = Recorder()
    agent = make_agent(repo_root, tmp_path, notifier=recorder)
    calls = []
    runner, _ = runner_for(agent, candles, "2026-03-04 16:50:00",
                           reviewer=lambda s, e, n: calls.append((s, e)) or {"summary": "ok", "reflections": 1, "proposals": 0})
    runner.run(max_ticks=15)
    text = recorder.joined()
    assert "Session khatam" in text and "AI review: ok" in text
    assert len(calls) == 1


def test_feed_errors_do_not_kill_the_loop(repo_root, tmp_path):
    candles = synthetic_candles(days=3, seed=2)
    recorder = Recorder()
    agent = make_agent(repo_root, tmp_path, notifier=recorder)
    runner, _ = runner_for(agent, candles, "2026-03-04 13:20:00", fail_times=1)
    runner.run(max_ticks=6)
    assert "Agent masla" in recorder.joined()
    assert recorder.signals  # it carried on after the failure


def test_calendar_failure_is_reported_not_fatal(repo_root, tmp_path):
    candles = synthetic_candles(days=3, seed=2)
    recorder = Recorder()
    agent = make_agent(repo_root, tmp_path, notifier=recorder)

    def broken():
        raise RuntimeError("offline")

    runner, _ = runner_for(agent, candles, "2026-03-04 13:20:00", calendar_loader=broken)
    runner.run(max_ticks=2)
    assert "calendar nahi mila" in recorder.joined()


def test_supports_forming():
    class Plain(Feed):
        def candles(self, pair, count):
            return pd.DataFrame()

    assert not supports_forming(Plain())
    assert supports_forming(FakeFeed(pd.DataFrame(), Clock("2026-01-05")))
