"""Economic calendar -> NewsEvents for the risk gate's blackout check.

Source: the Forex Factory weekly JSON feed, which is UNOFFICIAL — no documented
schema or terms. Off by default (settings `calendar.enabled`). Before turning it
on, open the URL in a browser, check the fields below still match, and check
the site's terms. Manual `/news` in Telegram always works as a fallback.

Expected items: {"title", "country" (currency code, e.g. "USD"), "date" (ISO with
UTC offset), "impact" ("High" | "Medium" | "Low" | "Holiday"), "forecast", "previous"}.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

from .news import NewsEvent

IMPACT = {"high": "high", "medium": "medium", "low": "low"}


def parse_ff_week(items: list[dict]) -> list[NewsEvent]:
    events = []
    for item in items or []:
        impact = IMPACT.get(str(item.get("impact", "")).strip().lower())
        currency = str(item.get("country", "")).strip().upper()
        if impact is None or len(currency) != 3 or not item.get("date"):
            continue  # holidays, non-economic items, unknown shapes
        stamp = pd.Timestamp(item["date"])
        if stamp.tzinfo is None:  # the feed's display timezone is New York
            stamp = stamp.tz_localize("America/New_York")
        events.append(NewsEvent(stamp.tz_convert("UTC"), currency, impact, str(item.get("title", "")).strip()))
    return sorted(events, key=lambda e: e.time_utc)


class CalendarError(RuntimeError):
    pass


def fetch_calendar(url: str, cache_path: Path | str, max_age_hours: float = 6, timeout: float = 15) -> list[NewsEvent]:
    """Events from cache if fresh, else download (falling back to a stale cache on failure)."""
    cache = Path(cache_path)
    fresh = cache.exists() and (time.time() - cache.stat().st_mtime) < max_age_hours * 3600
    if not fresh:
        request = urllib.request.Request(url, headers={"User-Agent": "ai-trader-agent (personal use)"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                items = json.loads(response.read().decode("utf-8"))
            if not isinstance(items, list):
                raise CalendarError("unexpected calendar format (not a list)")
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(items), encoding="utf-8")
        except (urllib.error.URLError, OSError, json.JSONDecodeError, CalendarError) as exc:
            if not cache.exists():
                raise CalendarError(f"calendar download failed: {exc}") from None
    return parse_ff_week(json.loads(cache.read_text(encoding="utf-8")))
