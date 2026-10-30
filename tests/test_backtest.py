import pandas as pd
import pytest

from conftest import synthetic_candles
from trader_agent.backtest.engine import BacktestConfig, run_backtest
from trader_agent.backtest.report import build_report, render_html, render_markdown, verdict, write_report
from trader_agent.gate import RiskGate
from trader_agent.ksor import risk_policy_from_dict, setup_from_dict
from trader_agent.stats import summarize


def setup(**changes):
    raw = {
        "id": "T01",
        "name": "every bullish candle",
        "version": 1,
        "status": "draft",
        "direction": "CALL",
        "pairs": ["EURUSD"],
        "sessions": ["london_newyork"],
        "conditions": ["bullish"],
    }
    raw.update(changes)
    return setup_from_dict(raw)


def test_trade_model_uses_next_open_and_expiry_close(sessions):
    candles = synthetic_candles(days=3, seed=4)
    result = run_backtest(candles, "EURUSD", [setup()], sessions, BacktestConfig(payout=0.8))
    trades = result.trades
    assert len(trades) > 50
    first = trades.iloc[0]
    assert first["entry_price"] == pytest.approx(candles.loc[first["entry_time"], "open"])
    exit_bar = first["exit_time"] - pd.Timedelta(minutes=1)
    assert first["exit_price"] == pytest.approx(candles.loc[exit_bar, "close"])
    expected = "WIN" if first["exit_price"] > first["entry_price"] else ("LOSS" if first["exit_price"] < first["entry_price"] else "DRAW")
    assert first["result"] == expected
    assert (trades["session"] == "london_newyork").all()


def test_trades_never_overlap(sessions):
    candles = synthetic_candles(days=3, seed=4)
    trades = run_backtest(candles, "EURUSD", [setup(expiry_minutes=3)], sessions).trades
    times = trades["bar_time"].sort_values().reset_index(drop=True)
    assert (times.diff().dropna() >= pd.Timedelta(minutes=3)).all()


def test_gap_in_data_skips_the_trade(sessions):
    candles = synthetic_candles(days=3, seed=4)
    result = run_backtest(candles.drop(candles.index[2200:2210]), "EURUSD", [setup(sessions=[])], sessions)
    assert result.diagnostics["skipped"].get("data_gap", 0) >= 1


def test_random_data_has_no_edge(sessions):
    """Honesty check: on random data a 'strategy' should land near 50% and never earn KEEP."""
    candles = synthetic_candles(days=20, seed=12)
    result = run_backtest(candles, "EURUSD", [setup()], sessions, BacktestConfig(payout=0.8))
    summary = summarize(result.trades["result"].tolist(), 0.8)
    assert 0.40 < summary["win_rate"] < 0.60
    report = build_report(result, {"synthetic": True})
    assert report["sections"][0]["verdict"] in ("WATCH", "DROP")


def test_gate_simulation_limits_losses(sessions):
    policy = risk_policy_from_dict({
        "version": 1, "status": "draft", "allowed_sessions": ["london_newyork"],
        "max_signals_per_day": 50, "max_losses_per_day": 3,
        "cooldown": {"after_consecutive_losses": 2, "minutes": 10},
    })
    candles = synthetic_candles(days=5, seed=6)
    result = run_backtest(candles, "EURUSD", [setup()], sessions, BacktestConfig(use_gate=True), RiskGate(policy, sessions))
    trades = result.trades.copy()
    trades["day"] = sessions.trading_day(pd.DatetimeIndex(trades["signal_time"]))
    assert (trades[trades["result"] == "LOSS"].groupby("day").size() <= 3).all()
    assert len(result.blocked) > 0


def test_out_of_sample_split_and_reports(sessions, tmp_path):
    candles = synthetic_candles(days=10, seed=3)
    config = BacktestConfig(oos_from=pd.Timestamp("2026-03-09", tz="UTC"))
    result = run_backtest(candles, "EURUSD", [setup()], sessions, config)
    assert set(result.trades["sample"]) == {"in", "out"}
    report = build_report(result, {"data": "synthetic", "synthetic": True})
    assert report["sections"][0]["judged_on"] == "out-of-sample"
    markdown = render_markdown(report)
    assert "SYNTHETIC" in markdown and "DRAFT" in markdown and "95% range" in markdown
    assert "<table>" in render_html(report)
    md_path, html_path = write_report(report, tmp_path, "bt")
    assert md_path.exists() and html_path.exists()


def test_verdict_rules():
    borderline = summarize(["WIN"] * 240 + ["LOSS"] * 160, 0.8)  # 60%, but range dips below 55.6%
    assert verdict(borderline, 0.8, 6)[0] == "WATCH"
    keep = summarize(["WIN"] * 260 + ["LOSS"] * 140, 0.8)  # 65% on 400 trades
    assert verdict(keep, 0.8, 6)[0] == "KEEP"
    assert verdict(keep, 0.4, 6)[0] == "WATCH"  # inconsistent months
    small = summarize(["WIN"] * 30 + ["LOSS"] * 10, 0.8)
    assert verdict(small, 1.0, 3)[0] == "WATCH"  # too few trades
    bad = summarize(["WIN"] * 90 + ["LOSS"] * 130, 0.8)
    assert verdict(bad, 0.0, 6)[0] == "DROP"
