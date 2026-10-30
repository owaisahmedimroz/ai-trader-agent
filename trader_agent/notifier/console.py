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

    def send_text(self, text: str, buttons=None) -> None:
        labels = " ".join(f"[{label}]" for row in (buttons or []) for label, _ in row)
        print(text + (f"\n{labels}" if labels else ""), file=self.stream)


class MultiNotifier:
    """Send the same message through several notifiers (e.g. console + Telegram).

    A failing channel (e.g. no internet for Telegram) must not stop the others.
    """

    def __init__(self, *notifiers, on_error=None):
        self.notifiers = [n for n in notifiers if n is not None]
        self.on_error = on_error

    def _each(self, method: str, *args) -> None:
        for notifier in self.notifiers:
            try:
                getattr(notifier, method)(*args)
            except Exception as exc:  # noqa: BLE001 — report and keep the other channels working
                if self.on_error:
                    self.on_error(notifier, exc)

    def send_signal(self, signal: dict, setup_name: str | None = None) -> None:
        self._each("send_signal", signal, setup_name)

    def send_text(self, text: str, buttons=None) -> None:
        self._each("send_text", text, buttons)
