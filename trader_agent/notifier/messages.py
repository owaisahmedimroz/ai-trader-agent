"""Message text (Roman Urdu) and button layouts — pure functions, easy to test."""

from __future__ import annotations

from ..timeutil import DISPLAY_TZ, to_display

ACTIONS = ("TAKEN", "SKIPPED")
RESULTS = ("WIN", "LOSS", "DRAW")
REVIEWS = ("normal", "agent_error", "execution_error", "news_spike")


def tz_label(tz: str) -> str:
    return "PKT" if tz == "Asia/Karachi" else tz


def pair_label(pair: str) -> str:
    return f"{pair[:3]}/{pair[3:]}"


def format_signal(signal: dict, setup_name: str | None = None, tz: str = DISPLAY_TZ) -> str:
    features = signal.get("features") or {}
    arrow = "🟢 CALL" if signal["direction"] == "CALL" else "🔴 PUT"
    setup = f"{signal['setup_id']} v{signal['setup_version']}" + (f" — {setup_name}" if setup_name else "")
    lines = [
        f"{arrow} — {pair_label(signal['pair'])}",
        f"⏰ Entry: {to_display(signal['signal_time'], tz)} {tz_label(tz)} | Expiry: {signal['expiry_minutes']} min",
        f"⛔ {to_display(signal['entry_deadline'], tz)} ke baad mat lagana",
        f"📖 Setup: {setup}",
        f"📊 Trend 15m: {features.get('m15_trend', '?')} | Regime: {features.get('regime', '?')} | Vol: {features.get('vol_state', '?')}",
    ]
    if signal.get("payout"):
        lines.append(f"💰 Payout: {signal['payout']:.0%}")
    mode = signal.get("mode", "live")
    lines.append(f"🧾 Signal #{signal['id']}" + ("" if mode == "live" else f" ({mode.upper()})"))
    return "\n".join(lines)


def action_buttons(signal_id: int) -> list[list[tuple[str, str]]]:
    return [[("✅ Lagaya", f"act:{signal_id}:TAKEN"), ("❌ Chhora", f"act:{signal_id}:SKIPPED")]]


def result_buttons(signal_id: int) -> list[list[tuple[str, str]]]:
    return [[("🏆 Win", f"res:{signal_id}:WIN"), ("💔 Loss", f"res:{signal_id}:LOSS"), ("➖ Draw", f"res:{signal_id}:DRAW")]]


def review_buttons(signal_id: int) -> list[list[tuple[str, str]]]:
    return [
        [("🎲 Normal loss", f"rev:{signal_id}:normal"), ("🐞 Agent ki ghalti", f"rev:{signal_id}:agent_error")],
        [("✋ Meri ghalti", f"rev:{signal_id}:execution_error"), ("📰 News/spike", f"rev:{signal_id}:news_spike")],
    ]


def parse_callback(data: str) -> tuple[str, int, str]:
    parts = (data or "").split(":")
    if len(parts) != 3 or not parts[1].isdigit():
        raise ValueError(f"bad button data {data!r}")
    kind, signal_id, value = parts[0], int(parts[1]), parts[2]
    allowed = {"act": ACTIONS, "res": RESULTS, "rev": REVIEWS}.get(kind)
    if allowed is None or value not in allowed:
        raise ValueError(f"bad button data {data!r}")
    return kind, signal_id, value


def format_day_summary(summary: dict, title: str = "Aaj") -> str:
    def rate(value):
        return "—" if value is None else f"{value * 100:.0f}%"

    return "\n".join(
        [
            f"📅 {title}",
            f"Signals: {summary['signals']} | Lagaye: {summary['taken']} | Chhore: {summary['skipped']} | Jawab nahi: {summary['no_action']}",
            f"Lagaye hue: {summary['taken_wins']} jeet / {summary['taken_losses']} haar / {summary['taken_draws']} draw "
            f"→ {rate(summary['taken_win_rate'])} | P&L: {summary['taken_pnl_units']:+.2f} units",
            f"Sab signals (feed): {rate(summary['all_win_rate'])} | Der se entries: {summary['late_entries']}",
            "Yaad rahe: ek din ka nateeja ittefaq ho sakta hai — faisla hafte/mahine ke data par.",
        ]
    )


def format_signal_detail(signal: dict, outcome: dict | None, action: dict | None, tz: str = DISPLAY_TZ) -> str:
    features = signal.get("features") or {}
    shown = ", ".join(f"{k}={v}" for k, v in sorted(features.items()))
    lines = [
        f"🧾 Signal #{signal['id']} — {signal['direction']} {pair_label(signal['pair'])} ({signal['mode']})",
        f"Waqt: {to_display(signal['signal_time'], tz, '%Y-%m-%d %H:%M')} {tz_label(tz)}",
        f"Setup: {signal['setup_id']} v{signal['setup_version']} | KSoR: {signal.get('ksor_commit') or '?'}",
        f"Features: {shown}",
        f"Aap ne: {action['action'] if action else 'jawab nahi diya'}",
        f"Nateeja: {outcome['result'] + ' (' + outcome['source'] + ')' if outcome else 'abhi nahi'}",
    ]
    return "\n".join(lines)


def help_text() -> str:
    return "\n".join(
        [
            "🤖 Commands:",
            "/status — agent aur limits ka haal",
            "/today — aaj ka score",
            "/last — akhri 5 signals",
            "/why 12 — signal #12 kyun diya",
            "/pause 30 — 30 minute signals band",
            "/stop — signals band (jab tak /resume na karein)",
            "/resume — dobara shuru",
            "/payout EURUSD 82 — Quotex ka payout batayein",
            "/news 18:30 USD high CPI — news ka waqt (PKT) — us waqt signals band",
        ]
    )


def format_status(info: dict) -> str:
    paused = info.get("paused_until")
    lines = [
        "📟 Status",
        f"Agent akhri baar: {info.get('last_seen') or 'abhi tak koi decision nahi'}",
        f"Halat: {'⛔ STOP' if info.get('stopped') else ('⏸ PAUSE ' + paused if paused else '🟢 chal raha')}",
        f"Aaj: {info.get('signals', 0)} signals, {info.get('losses', 0)} loss (limit {info.get('max_losses', '?')})",
        f"Approved setups: {info.get('approved_setups', 0)} | Risk policy: {info.get('policy_status', '?')}",
        f"Payouts: {info.get('payouts') or 'default'}",
        f"News blackouts: {info.get('news_count', 0)}",
    ]
    return "\n".join(lines)
