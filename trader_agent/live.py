"""Phase 2 — the live loop.

Every minute: optional heads-up at ~:45 (setup forming), then right after the
candle closes: fetch candles -> agents -> GO signal or CANCEL. Around that:
heartbeat, broker-result prompts, session start (briefing) and session end
(daily summary, drift check, nightly AI review).

Time and sleeping are injectable so tests can drive the loop with a fake clock.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

import pandas as pd

from .briefing import briefing_facts
from .feeds.base import Feed
from .learning import check_drift
from .notifier.messages import (
    format_cancel,
    format_day_summary,
    format_heads_up,
    format_heartbeat,
    format_result_prompt,
    result_buttons,
)
from .pipeline import NullNotifier

log = logging.getLogger("trader_agent.live")


def supports_forming(feed) -> bool:
    method = getattr(type(feed), "candles_with_forming", None)
    return method is not None and method is not Feed.candles_with_forming


class LiveRunner:
    def __init__(self, agents: list, feed, notifier, *, briefer: Callable[[str], str | None] | None = None,
                 reviewer: Callable[[pd.Timestamp, pd.Timestamp, pd.Timestamp], dict] | None = None,
                 calendar_loader: Callable[[], list] | None = None,
                 now: Callable[[], pd.Timestamp] | None = None, sleep: Callable[[float], None] | None = None):
        if not agents:
            raise ValueError("LiveRunner needs at least one agent")
        self.agents = agents
        self.primary = agents[0]  # its settings, sessions and policy drive timing and messages
        self.feed = feed
        self.notifier = notifier
        self.briefer = briefer
        self.reviewer = reviewer
        self.calendar_loader = calendar_loader
        self._now = now or (lambda: pd.Timestamp.now(tz="UTC"))
        self._sleep = sleep or time.sleep
        live = self.primary.settings.live
        self.pairs = list(self.primary.settings.pairs)
        self.lookback = int(self.primary.settings.lookback_bars)
        self.settle = float(live["settle_seconds"])
        self.heads_up_enabled = bool(live["heads_up"]) and supports_forming(feed)
        self.heads_up_second = int(live["heads_up_second"])
        self.result_delay = pd.Timedelta(seconds=int(live["result_prompt_delay_seconds"]))
        self.heartbeat_every = pd.Timedelta(minutes=int(live["heartbeat_minutes"]))
        self.tz = self.primary.settings.display_timezone
        self.in_session: bool | None = None
        self.last_heartbeat: pd.Timestamp | None = None
        self.prompted: set[int] = set()
        self.heads_ups: dict[tuple[str, str, pd.Timestamp], bool] = {}
        self.errors = 0
        self.stopped = False

    # ---- main loop -----------------------------------------------------------------

    def run(self, max_ticks: int | None = None) -> None:
        self.refresh_calendar()
        self.notifier.send_text(f"✅ Agent online — {', '.join(self.pairs)} | mode: {', '.join(a.mode for a in self.agents)}")
        ticks = 0
        while not self.stopped:
            now = self._now()
            minute = now.floor("min")
            close = minute + pd.Timedelta(minutes=1)
            heads_up_at = minute + pd.Timedelta(seconds=self.heads_up_second)
            if self.heads_up_enabled and now < heads_up_at and self.primary.might_signal(close):
                self._sleep_until(heads_up_at)
                self._guard(self.heads_up, close)
            self._sleep_until(close + pd.Timedelta(seconds=self.settle))
            self._guard(self.tick, close)
            ticks += 1
            if max_ticks is not None and ticks >= max_ticks:
                break

    def _sleep_until(self, target: pd.Timestamp) -> None:
        seconds = (target - self._now()).total_seconds()
        if seconds > 0:
            self._sleep(seconds)

    def _guard(self, fn, *args) -> None:
        """Run one step; on errors alert (not every time) and back off, but never die."""
        try:
            fn(*args)
            self.errors = 0
        except Exception as exc:  # noqa: BLE001 — the loop must survive feed/network hiccups
            self.errors += 1
            log.exception("live step failed")
            if self.errors in (1, 5, 20) or self.errors % 100 == 0:
                self.notifier.send_text(f"⚠️ Agent masla ({self.errors}x): {type(exc).__name__}: {exc}")
            self._sleep(min(60.0, 2.0 ** min(self.errors, 6)))

    # ---- steps -----------------------------------------------------------------------

    def refresh_calendar(self) -> None:
        if self.calendar_loader is None:
            return
        try:
            events = self.calendar_loader()
        except Exception as exc:  # noqa: BLE001 — calendar is optional; manual /news still works
            self.notifier.send_text(f"⚠️ Economic calendar nahi mila ({exc}). Bari news /news se daalein.")
            return
        for agent in self.agents:
            agent.calendar_events = list(events)

    def heads_up(self, close: pd.Timestamp) -> None:
        """~15 s before the close: warn if a setup is forming. Records nothing."""
        for pair in self.pairs:
            candles = self.feed.candles_with_forming(pair, self.lookback)
            if candles.empty or candles.index[-1] != close - pd.Timedelta(minutes=1):
                continue
            for agent in self.agents:
                if isinstance(agent.notifier, NullNotifier):
                    continue  # silent shadow agents never announce
                for candidate in agent.preview(pair, candles):
                    key = (pair, candidate.setup_id, candidate.signal_time)
                    if key not in self.heads_ups:
                        self.heads_ups[key] = True
                        self.notifier.send_text(format_heads_up(candidate, self.tz))

    def tick(self, close: pd.Timestamp) -> None:
        self._session_events(close)
        for pair in self.pairs:
            candles = self._closed_candles(pair, close)
            if candles is None:
                continue
            lag = self.feed.lag_seconds(pair)
            sent = []
            for agent in self.agents:
                sent += [agent.ssor.get_signal(i) for i in agent.on_closed_candle(pair, candles, lag)]
            self._cancel_unconfirmed(pair, close, sent)
        self._result_prompts(close)
        self._heartbeat(close)

    def _closed_candles(self, pair: str, close: pd.Timestamp, attempts: int = 8):
        """Latest closed candles; waits briefly if the feed has not published the new candle yet."""
        expected = close - pd.Timedelta(minutes=1)
        for attempt in range(attempts):
            candles = self.feed.candles(pair, self.lookback)
            if not candles.empty and candles.index[-1] >= expected:
                return candles[candles.index <= expected]
            self._sleep(0.5 * (attempt + 1))
        if self.primary.sessions.market_open(close):
            log.warning("no fresh candle for %s at %s", pair, close)
        return None

    def _cancel_unconfirmed(self, pair: str, close: pd.Timestamp, sent: list[dict]) -> None:
        confirmed = {(s["pair"], s["setup_id"]) for s in sent if s}
        for key in [k for k in self.heads_ups if k[0] == pair and k[2] == close]:
            if (key[0], key[1]) not in confirmed:
                self.notifier.send_text(format_cancel(pair, key[1], close, self.tz))
            del self.heads_ups[key]

    def _result_prompts(self, close: pd.Timestamp) -> None:
        now = self._now()
        for agent in self.agents:
            if agent.mode != "live":
                continue
            day_start, day_end = agent.sessions.trading_day_bounds(agent.sessions.trading_day_of(close))
            for signal in agent.ssor.taken_without_broker_result(day_start - pd.Timedelta(days=1), day_end):
                exit_time = pd.Timestamp(signal["signal_time"]) + pd.Timedelta(minutes=signal["expiry_minutes"])
                if signal["id"] in self.prompted or now < exit_time + self.result_delay:
                    continue
                self.prompted.add(signal["id"])
                self.notifier.send_text(format_result_prompt(signal, self.tz), result_buttons(signal["id"]))

    def _heartbeat(self, close: pd.Timestamp) -> None:
        if not self.in_session:
            return
        if self.last_heartbeat is not None and close - self.last_heartbeat < self.heartbeat_every:
            return
        self.last_heartbeat = close
        agent = self.primary
        day_start, day_end = agent.sessions.trading_day_bounds(agent.sessions.trading_day_of(close))
        signals = len(agent.ssor.signals_between(day_start, day_end, mode=agent.mode))
        lags = [lag for pair in self.pairs if (lag := self.feed.lag_seconds(pair)) is not None]
        self.notifier.send_text(format_heartbeat({"pairs": self.pairs, "signals": signals, "lag": max(lags) if lags else None}))

    def _session_events(self, close: pd.Timestamp) -> None:
        now_in = self.primary.might_signal(close)
        was_in, self.in_session = self.in_session, now_in
        if was_in is None or was_in == now_in:
            return
        if now_in:
            self._session_start(close)
        else:
            self._session_end(close)

    def _session_start(self, close: pd.Timestamp) -> None:
        self.refresh_calendar()
        self.last_heartbeat = close
        candles = {pair: self.feed.candles(pair, self.lookback) for pair in self.pairs}
        facts = briefing_facts(self.primary, candles, close)
        self.notifier.send_text(facts)
        if self.briefer is not None:
            commentary = self.briefer(facts)
            if commentary:
                self.notifier.send_text(commentary)

    def _session_end(self, close: pd.Timestamp) -> None:
        agent = self.primary
        day = agent.sessions.trading_day_of(close - pd.Timedelta(minutes=1))
        start, end = agent.sessions.trading_day_bounds(day)
        summary = agent.ssor.day_summary(start, end, mode=agent.mode)
        self.notifier.send_text(format_day_summary(summary, title=f"Session khatam ({day})"))
        for live_agent in self.agents:
            check_drift(live_agent, self.notifier, close)
        if self.reviewer is not None:
            try:
                result = self.reviewer(start, end, close)
                self.notifier.send_text(
                    f"🌙 AI review: {result['summary']}\n"
                    f"Sabaq: {result['reflections']} · nayi tajaweez: {result['proposals']} (/proposals)"
                )
            except Exception as exc:  # noqa: BLE001 — the review is optional
                self.notifier.send_text(f"⚠️ Raat ka AI review nahi ho saka: {type(exc).__name__}")
