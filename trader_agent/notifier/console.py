"""Prints signals to the terminal (replay / testing)."""

from __future__ import annotations

import sys

from ..timeutil import DISPLAY_TZ
from .messages import format_signal


class ConsoleNotifier:
    def __init__(self, tz: str = DISPLAY_TZ, stream=None):
        self.tz = tz
        self.stream = stream or sys.stdout

    def send_signal(self, signal: dict, setup_name: str | None = None) -> None:
        print("\n" + format_signal(signal, setup_name, self.tz) + "\n[✅ Lagaya] [❌ Chhora]", file=self.stream)

    def send_text(self, text: str) -> None:
        print(text, file=self.stream)


class MultiNotifier:
    """Send the same message through several notifiers (e.g. console + Telegram)."""

    def __init__(self, *notifiers):
        self.notifiers = [n for n in notifiers if n is not None]

    def send_signal(self, signal: dict, setup_name: str | None = None) -> None:
        for notifier in self.notifiers:
            notifier.send_signal(signal, setup_name)

    def send_text(self, text: str) -> None:
        for notifier in self.notifiers:
            notifier.send_text(text)
