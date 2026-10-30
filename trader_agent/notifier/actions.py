"""What happens when the human presses a button or types a command.

Pure logic over SSoR and the control file, so it can be tested without Telegram.
"""

from __future__ import annotations

import pandas as pd

from ..ssor import SSoR
from ..timeutil import as_utc
from .messages import parse_callback, result_buttons, review_buttons


def apply_callback(ssor: SSoR, data: str, now) -> tuple[str, list | None]:
    """Record a button press. Returns (reply text, next buttons or None)."""
    kind, signal_id, value = parse_callback(data)
    signal = ssor.get_signal(signal_id)
    if signal is None:
        return f"Signal #{signal_id} nahi mila.", None
    now = as_utc(now)
    if kind == "act":
        ssor.record_action(signal_id, value, now)
        if value == "SKIPPED":
            return f"❌ #{signal_id} chhor diya. Result phir bhi record hoga (seekhne ke liye).", None
        late = (now - pd.Timestamp(signal["entry_deadline"])).total_seconds()
        warning = f" ⚠️ {late:.0f}s der se — agli dafa waqt par" if late > 0 else ""
        return f"✅ #{signal_id} lagaya.{warning}\nExpiry ke baad Quotex ka result batayein:", result_buttons(signal_id)
    if kind == "res":
        ssor.record_outcome(signal_id, "broker", value, now)
        if value == "LOSS":
            return f"💔 #{signal_id} loss save. Is loss ki qisam kya thi?", review_buttons(signal_id)
        icon = "🏆" if value == "WIN" else "➖"
        return f"{icon} #{signal_id} {value} save.", None
    ssor.record_review(signal_id, value, now)
    return f"📝 #{signal_id} review save. Shukriya!", None


def parse_payout(args: list[str]) -> tuple[str, float]:
    """['EURUSD', '82'] or ['EURUSD', '0.82'] -> ('EURUSD', 0.82)."""
    if len(args) != 2:
        raise ValueError("format: /payout EURUSD 82")
    pair, raw = args[0].upper(), float(args[1].rstrip("%"))
    if len(pair) != 6 or not pair.isalpha():
        raise ValueError("pair EURUSD jaisa likhein")
    payout = raw / 100 if raw > 1.5 else raw
    if not 0.3 <= payout <= 1.0:
        raise ValueError("payout 30% se 100% ke darmiyan hona chahiye")
    return pair, round(payout, 4)


def parse_pause(args: list[str]) -> int:
    if len(args) != 1 or not args[0].isdigit():
        raise ValueError("format: /pause 30")
    minutes = int(args[0])
    if not 1 <= minutes <= 600:
        raise ValueError("1 se 600 minute tak")
    return minutes
