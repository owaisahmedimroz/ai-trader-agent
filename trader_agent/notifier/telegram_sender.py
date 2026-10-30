"""Outbound Telegram messages through the Bot HTTP API (standard library only).

Used by the replay/live loop to push signals with buttons. Button presses are
handled by the separate bot program (telegram_bot.py), which can run at the
same time — sending does not interfere with the bot's polling.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from ..timeutil import DISPLAY_TZ
from .messages import action_buttons, format_signal


class TelegramError(RuntimeError):
    pass


def keyboard(buttons: list[list[tuple[str, str]]] | None) -> dict | None:
    if not buttons:
        return None
    return {"inline_keyboard": [[{"text": text, "callback_data": data} for text, data in row] for row in buttons]}


class TelegramSender:
    def __init__(self, token: str, chat_id: str | int | None = None, tz: str = DISPLAY_TZ, timeout: float = 10.0):
        if not token:
            raise TelegramError("TELEGRAM_BOT_TOKEN .env mein chahiye")
        self._token = token
        self.chat_id = int(chat_id) if chat_id else None
        self.tz = tz
        self.timeout = timeout

    def call(self, method: str, payload: dict) -> dict:
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{self._token}/{method}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # never include the token in errors
            raise TelegramError(f"Telegram {method} failed: HTTP {exc.code}") from None
        except urllib.error.URLError as exc:
            raise TelegramError(f"Telegram {method} failed: {exc.reason}") from None
        if not body.get("ok"):
            raise TelegramError(f"Telegram {method} failed: {body.get('description')}")
        return body["result"]

    def send_text(self, text: str, buttons=None) -> dict:
        if self.chat_id is None:
            raise TelegramError("TELEGRAM_CHAT_ID .env mein chahiye (bot ko /start bhej kar maloom karein)")
        payload = {"chat_id": self.chat_id, "text": text}
        markup = keyboard(buttons)
        if markup:
            payload["reply_markup"] = markup
        return self.call("sendMessage", payload)

    def send_signal(self, signal: dict, setup_name: str | None = None) -> dict:
        return self.send_text(format_signal(signal, setup_name, self.tz), action_buttons(signal["id"]))

    def whoami(self) -> dict:
        return self.call("getMe", {})
