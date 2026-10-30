"""Economic news events and blackout windows.

Phase 1 sources: a CSV file (time_utc,currency,impact,title) or events typed in
by hand (Telegram `/news 18:30 USD high CPI`). An automatic calendar feed comes
in Phase 2.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .timeutil import DISPLAY_TZ, as_utc

IMPACTS = ("high", "medium", "low")


@dataclass(frozen=True)
class NewsEvent:
    time_utc: pd.Timestamp
    currency: str
    impact: str
    title: str = ""


def pair_currencies(pair: str) -> tuple[str, str]:
    pair = pair.upper()
    return pair[:3], pair[3:6]


def load_events_csv(path: Path | str) -> list[NewsEvent]:
    events = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            impact = row["impact"].strip().lower()
            if impact not in IMPACTS:
                raise ValueError(f"unknown impact {impact!r} in {path}")
            events.append(
                NewsEvent(as_utc(pd.Timestamp(row["time_utc"])), row["currency"].strip().upper(), impact, row.get("title", "").strip())
            )
    return sorted(events, key=lambda e: e.time_utc)


def parse_manual(text: str, today: date, tz: str = DISPLAY_TZ) -> NewsEvent:
    """'18:30 USD high CPI' (time in the display timezone) -> NewsEvent in UTC."""
    parts = text.split()
    if len(parts) < 2:
        raise ValueError("format: HH:MM CUR [high|medium|low] [title]")
    hh, mm = (int(x) for x in parts[0].split(":"))
    currency = parts[1].upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValueError(f"currency should be 3 letters like USD, got {parts[1]!r}")
    impact, rest = "high", parts[2:]
    if rest and rest[0].lower() in IMPACTS:
        impact, rest = rest[0].lower(), rest[1:]
    local = datetime(today.year, today.month, today.day, hh, mm, tzinfo=ZoneInfo(tz))
    return NewsEvent(as_utc(pd.Timestamp(local)), currency, impact, " ".join(rest))


def _relevant(events, pair: str, impacts) -> list[NewsEvent]:
    currencies = set(pair_currencies(pair))
    return [e for e in events if e.currency in currencies and e.impact in impacts]


def blackout_reason(events, pair: str, now, minutes_before: int, minutes_after: int, impacts=("high",)) -> str | None:
    now = as_utc(now)
    for event in _relevant(events, pair, impacts):
        start = event.time_utc - pd.Timedelta(minutes=minutes_before)
        end = event.time_utc + pd.Timedelta(minutes=minutes_after)
        if start <= now <= end:
            label = f"{event.title} " if event.title else ""
            return f"news blackout: {label}({event.currency}, {event.impact}) at {event.time_utc:%H:%M} UTC"
    return None


def blackout_mask(events, pair: str, index: pd.DatetimeIndex, minutes_before: int, minutes_after: int, impacts=("high",)) -> np.ndarray:
    """Vectorised version for backtests: True where a decision time is inside a blackout."""
    mask = np.zeros(len(index), dtype=bool)
    values = index.tz_convert("UTC")
    for event in _relevant(events, pair, impacts):
        start = event.time_utc - pd.Timedelta(minutes=minutes_before)
        end = event.time_utc + pd.Timedelta(minutes=minutes_after)
        mask |= np.asarray((values >= start) & (values <= end))
    return mask
