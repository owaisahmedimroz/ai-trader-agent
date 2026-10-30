"""Shared fakes for live-loop and AI tests (no network, no MT5, no API key)."""

from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pandas as pd

from trader_agent.config import load_settings
from trader_agent.gate import RiskGate
from trader_agent.ksor import risk_policy_from_dict, setup_from_dict
from trader_agent.pipeline import Agent
from trader_agent.ssor import SSoR
from trader_agent.timeutil import SessionBook

POLICY = {
    "version": 1, "status": "draft", "allowed_sessions": ["london_newyork"],
    "max_signals_per_day": 50, "max_losses_per_day": 50,
    "cooldown": {"after_consecutive_losses": 99, "minutes": 1}, "min_minutes_between_signals": 2,
    "entry_window_seconds": 10,
}


class Recorder:
    """Notifier that keeps everything it is asked to send."""

    def __init__(self, on_signal=None):
        self.signals, self.texts = [], []
        self.on_signal = on_signal

    def send_signal(self, signal, setup_name=None):
        self.signals.append(signal)
        if self.on_signal:
            self.on_signal(signal)

    def send_text(self, text, buttons=None):
        self.texts.append((text, buttons))

    def joined(self) -> str:
        return "\n".join(t for t, _ in self.texts)


def make_agent(repo_root, tmp_path, mode="live", conditions=("bullish",), notifier=None, setup_id="T01", policy=None, lookback=2000):
    settings = replace(load_settings(root=repo_root), lookback_bars=lookback, db_path=tmp_path / "ssor.sqlite3")
    sessions = SessionBook.from_yaml(settings.sessions_path)
    risk = risk_policy_from_dict(policy or POLICY, sessions.names())
    setup = setup_from_dict({
        "id": setup_id, "name": "test setup", "version": 1, "status": "approved", "approved_by": "test",
        "approved_on": "2026-01-01", "direction": "CALL", "pairs": ["EURUSD"], "sessions": ["london_newyork"],
        "conditions": list(conditions),
    })
    return Agent(
        settings=settings, sessions=sessions, setups=[setup], policy=risk, gate=RiskGate(risk, sessions),
        ssor=SSoR(tmp_path / "ssor.sqlite3"), notifier=notifier or Recorder(), mode=mode,
        control_path=tmp_path / "control.json", ksor_version="test", count_only_taken=(mode == "live"),
    )


class Clock:
    def __init__(self, start: str):
        self.now = pd.Timestamp(start, tz="UTC")

    def __call__(self) -> pd.Timestamp:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += pd.Timedelta(seconds=seconds)


class FakeFeed:
    """Serves historical candles as if they were live at `clock.now`."""

    def __init__(self, candles: pd.DataFrame, clock: Clock, forming=None, fail_times: int = 0):
        self.data, self.clock, self.forming, self.fail_times = candles, clock, forming, fail_times

    def candles(self, pair, count):
        if self.fail_times:
            self.fail_times -= 1
            raise ConnectionError("feed down")
        cutoff = self.clock.now.floor("min")
        return self.data[self.data.index < cutoff].tail(count)

    def candles_with_forming(self, pair, count):
        cutoff = self.clock.now.floor("min")
        closed = self.data[self.data.index < cutoff].tail(count)
        if cutoff not in self.data.index:
            return closed
        row = self.data.loc[[cutoff]].copy()
        if self.forming:
            row = self.forming(row)
        return pd.concat([closed, row])

    def lag_seconds(self, pair):
        return 0.4


class FakeSDK:
    """Stands in for anthropic.Anthropic(): returns canned JSON, records requests."""

    def __init__(self, payload=None, stop_reason="end_turn", error=None):
        self.payload, self.stop_reason, self.error = payload or {}, stop_reason, error
        self.requests, self.options = [], []
        self.messages = SimpleNamespace(create=self._create, stream=self._stream)

    def with_options(self, **options):
        self.options.append(options)
        return self

    def _response(self):
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=json.dumps(self.payload))],
            usage=SimpleNamespace(input_tokens=120, output_tokens=30, cache_read_input_tokens=0, cache_creation_input_tokens=0),
            stop_reason=self.stop_reason,
        )

    def _create(self, **request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return self._response()

    def _stream(self, **request):
        self.requests.append(request)
        sdk = self

        class _Stream:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def get_final_message(self):
                return sdk._response()

        return _Stream()
