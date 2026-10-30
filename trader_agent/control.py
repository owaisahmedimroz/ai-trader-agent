"""Controls the risk gate obeys: /stop, /pause, /payout, /news and paused setups.

Kept in a small JSON file (data/control.json) so the Telegram bot and the agent
loop can share it even when they run as separate programs. Humans change it via
Telegram; the deterministic drift check (learning.py) may pause a setup. The AI
never writes it.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

from .news import NewsEvent
from .timeutil import as_utc


@dataclass
class Control:
    stopped: bool = False
    paused_until: str | None = None  # ISO UTC
    payouts: dict[str, float] = field(default_factory=dict)
    news: list[dict] = field(default_factory=list)  # {time_utc, currency, impact, title}
    paused_setups: dict[str, str] = field(default_factory=dict)  # setup id -> reason

    @classmethod
    def load(cls, path: Path | str) -> "Control":
        path = Path(path)
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        return cls(
            stopped=bool(raw.get("stopped", False)),
            paused_until=raw.get("paused_until"),
            payouts={k.upper(): float(v) for k, v in (raw.get("payouts") or {}).items()},
            news=list(raw.get("news") or []),
            paused_setups={k.upper(): str(v) for k, v in (raw.get("paused_setups") or {}).items()},
        )

    def save(self, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        os.replace(tmp, path)  # atomic on Windows and Linux

    def paused_until_ts(self) -> pd.Timestamp | None:
        return None if not self.paused_until else as_utc(pd.Timestamp(self.paused_until))

    def pause(self, minutes: int, now) -> None:
        self.paused_until = (as_utc(now) + pd.Timedelta(minutes=minutes)).isoformat()

    def resume(self) -> None:
        self.stopped = False
        self.paused_until = None

    def add_news(self, event: NewsEvent) -> None:
        self.news.append(
            {"time_utc": event.time_utc.isoformat(), "currency": event.currency, "impact": event.impact, "title": event.title}
        )

    def events(self) -> list[NewsEvent]:
        return [
            NewsEvent(as_utc(pd.Timestamp(e["time_utc"])), e["currency"].upper(), e["impact"].lower(), e.get("title", ""))
            for e in self.news
        ]
