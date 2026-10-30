"""Market sessions, forex trading days and display time (DST-safe).

Everything inside the agent is UTC. Session hours are written in each market's
*local* time (ksor/sessions.yaml) and converted with zoneinfo, so daylight-saving
changes in London, New York and Sydney are handled automatically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

DISPLAY_TZ = "Asia/Karachi"


def _parse_hhmm(value) -> time:
    hours, minutes = str(value).split(":")
    return time(int(hours), int(minutes))


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def as_utc(ts) -> pd.Timestamp:
    ts = pd.Timestamp(ts)
    if ts.tzinfo is None:
        raise ValueError(f"timestamp must be timezone-aware: {ts}")
    return ts.tz_convert("UTC")


def as_utc_index(index) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(index)
    if idx.tz is None:
        raise ValueError("timestamps must be timezone-aware (UTC)")
    return idx.tz_convert("UTC")


def to_display(ts, tz: str = DISPLAY_TZ, fmt: str = "%H:%M:%S") -> str:
    return as_utc(ts).tz_convert(tz).strftime(fmt)


@dataclass(frozen=True)
class Session:
    name: str
    tz: str
    open: time
    close: time

    def mask(self, index) -> np.ndarray:
        local = as_utc_index(index).tz_convert(self.tz)
        mins = np.asarray(local.hour * 60 + local.minute)
        start, end = _minutes(self.open), _minutes(self.close)
        if start < end:
            inside = (mins >= start) & (mins < end)
        else:  # session crosses local midnight
            inside = (mins >= start) | (mins < end)
        return inside & (np.asarray(local.day_of_week) < 5)


@dataclass
class SessionBook:
    sessions: dict[str, Session]
    overlaps: dict[str, tuple[str, ...]] = field(default_factory=dict)
    rollover_tz: str = "America/New_York"
    rollover_time: time = time(17, 0)

    @classmethod
    def from_yaml(cls, path: Path | str) -> "SessionBook":
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        sessions = {
            name: Session(name, spec["tz"], _parse_hhmm(spec["open"]), _parse_hhmm(spec["close"]))
            for name, spec in (raw.get("sessions") or {}).items()
        }
        overlaps = {name: tuple(members) for name, members in (raw.get("overlaps") or {}).items()}
        for name, members in overlaps.items():
            unknown = [m for m in members if m not in sessions]
            if unknown:
                raise ValueError(f"overlap {name!r} uses unknown sessions: {unknown}")
        rollover = raw.get("trading_day_rollover") or {}
        return cls(
            sessions=sessions,
            overlaps=overlaps,
            rollover_tz=rollover.get("tz", "America/New_York"),
            rollover_time=_parse_hhmm(rollover.get("time", "17:00")),
        )

    def names(self) -> list[str]:
        return list(self.sessions) + list(self.overlaps)

    def mask(self, name: str, index) -> np.ndarray:
        if name in self.sessions:
            return self.sessions[name].mask(index)
        if name in self.overlaps:
            result = np.ones(len(index), dtype=bool)
            for member in self.overlaps[name]:
                result &= self.sessions[member].mask(index)
            return result
        raise KeyError(f"unknown session {name!r}; known: {self.names()}")

    def contains(self, name: str, ts) -> bool:
        return bool(self.mask(name, pd.DatetimeIndex([as_utc(ts)]))[0])

    def market_open_mask(self, index) -> np.ndarray:
        """Forex is closed from Friday 17:00 to Sunday 17:00 New York time."""
        local = as_utc_index(index).tz_convert(self.rollover_tz)
        mins = np.asarray(local.hour * 60 + local.minute)
        weekday = np.asarray(local.day_of_week)
        cut = _minutes(self.rollover_time)
        closed = (weekday == 5) | ((weekday == 4) & (mins >= cut)) | ((weekday == 6) & (mins < cut))
        return ~closed

    def market_open(self, ts) -> bool:
        return bool(self.market_open_mask(pd.DatetimeIndex([as_utc(ts)]))[0])

    def trading_day(self, index) -> np.ndarray:
        """Forex trading-day label for each timestamp (a day starts at 17:00 New York)."""
        local = as_utc_index(index).tz_convert(self.rollover_tz)
        shift = pd.Timedelta(hours=24) - pd.Timedelta(
            hours=self.rollover_time.hour, minutes=self.rollover_time.minute
        )
        return np.asarray((local + shift).date)

    def trading_day_of(self, ts) -> date:
        return self.trading_day(pd.DatetimeIndex([as_utc(ts)]))[0]

    def trading_day_bounds(self, day: date) -> tuple[pd.Timestamp, pd.Timestamp]:
        """UTC start/end of a forex trading day (previous day 17:00 → this day 17:00 New York)."""
        end_local = pd.Timestamp(
            year=day.year, month=day.month, day=day.day,
            hour=self.rollover_time.hour, minute=self.rollover_time.minute,
        ).tz_localize(self.rollover_tz)
        start_local = (end_local.tz_localize(None) - pd.Timedelta(days=1)).tz_localize(self.rollover_tz)
        return start_local.tz_convert("UTC"), end_local.tz_convert("UTC")
