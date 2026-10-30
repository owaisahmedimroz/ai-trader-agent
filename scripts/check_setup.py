"""Check that this PC is ready: Python, packages, .env keys, KSoR files, and
optionally the MT5 connection and the Telegram bot token.

    python scripts/check_setup.py
    python scripts/check_setup.py --mt5 --telegram

Secret values are never printed — only whether they are set.
"""

from __future__ import annotations

import argparse
import importlib
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OK, WARN, FAIL = "✅", "⚠️ ", "❌"


def line(mark: str, text: str) -> None:
    print(f"{mark} {text}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mt5", action="store_true", help="connect to MT5 and read a few candles")
    parser.add_argument("--telegram", action="store_true", help="check the bot token with Telegram")
    args = parser.parse_args()
    failures = 0

    version = sys.version_info
    if (version.major, version.minor) in ((3, 11), (3, 12)):
        line(OK, f"Python {platform.python_version()}")
    else:
        line(WARN, f"Python {platform.python_version()} — 3.11 ya 3.12 behtar hai (MT5 package ke liye)")

    packages = ["pandas", "numpy", "yaml", "dotenv", "telegram"]
    if sys.platform == "win32":
        packages += ["tzdata", "MetaTrader5"]
    for name in packages:
        try:
            module = importlib.import_module(name)
            line(OK, f"{name} {getattr(module, '__version__', '')}".strip())
        except ImportError:
            line(FAIL, f"{name} nahi mila — pip install -r requirements.txt")
            failures += 1

    try:
        from zoneinfo import ZoneInfo

        ZoneInfo("Asia/Karachi")
        ZoneInfo("America/New_York")
        line(OK, "Timezones (zoneinfo)")
    except Exception as exc:  # noqa: BLE001 — report any timezone problem plainly
        line(FAIL, f"Timezones kaam nahi kar rahe ({exc}) — pip install tzdata")
        failures += 1

    from trader_agent.config import SECRET_KEYS, load_secrets, load_settings
    from trader_agent.features import feature_names
    from trader_agent.ksor import KsorError, governance_warnings, load_risk_policy, load_setups
    from trader_agent.ssor import SSoR
    from trader_agent.timeutil import SessionBook

    settings = load_settings()
    secrets = load_secrets()
    env_file = ROOT / ".env"
    line(OK if env_file.exists() else WARN, ".env file " + ("mili" if env_file.exists() else "nahi mili (.env.example copy karein)"))
    for key in SECRET_KEYS:
        line(OK if key in secrets else WARN, f"{key} {'set hai' if key in secrets else 'khali hai'}")

    try:
        sessions = SessionBook.from_yaml(settings.sessions_path)
        line(OK, f"Sessions: {', '.join(sessions.names())}")
        policy = load_risk_policy(settings.risk_policy_path, sessions.names())
        line(OK if policy.status == "approved" else WARN, f"Risk policy v{policy.version}: {policy.status}")
        everything = load_setups(settings.setups_dir, ("draft", "approved", "retired"), feature_names(sessions), sessions.names())
        counts = {s: sum(x.status == s for x in everything) for s in ("approved", "draft", "retired")}
        line(OK, f"Setups: {counts['approved']} approved, {counts['draft']} draft, {counts['retired']} retired")
        changelog = (settings.ksor_dir / "CHANGELOG.md").read_text(encoding="utf-8")
        for warning in governance_warnings(everything, changelog):
            line(WARN, warning)
        if counts["approved"] == 0:
            line(WARN, "Abhi koi approved setup nahi — live signals ke liye Ustad ke setups approve karne honge")
    except (KsorError, OSError, ValueError) as exc:
        line(FAIL, f"KSoR: {exc}")
        failures += 1

    try:
        with SSoR(settings.db_path):
            pass
        line(OK, f"SSoR database: {settings.db_path}")
    except Exception as exc:  # noqa: BLE001
        line(FAIL, f"SSoR database nahi khul saka: {exc}")
        failures += 1

    if args.mt5:
        failures += check_mt5(settings, secrets)
    if args.telegram:
        failures += check_telegram(secrets)

    print("\n" + ("Sab theek hai ✅" if failures == 0 else f"{failures} masle — upar ❌ dekhein"))
    return 0 if failures == 0 else 1


def check_mt5(settings, secrets) -> int:
    if sys.platform != "win32":
        line(FAIL, "MT5 sirf Windows par chalta hai")
        return 1
    missing = [k for k in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER") if k not in secrets]
    if missing:
        line(FAIL, f".env mein {missing} chahiye")
        return 1
    import pandas as pd

    from trader_agent.feeds.mt5_feed import MT5Feed
    from trader_agent.timeutil import SessionBook

    try:
        feed = MT5Feed(secrets["MT5_LOGIN"], secrets["MT5_PASSWORD"], secrets["MT5_SERVER"],
                       settings.mt5_symbols, settings.mt5_server_utc_offset_hours)
        pair = settings.pairs[0]
        candles = feed.candles(pair, 10)
        offset = feed.server_offset(pair)
        last = candles.index[-1]
        now = pd.Timestamp.now(tz="UTC")
        age = (now - last).total_seconds() / 60
        line(OK, f"MT5 connected. {pair} akhri candle {last} UTC ({age:.1f} min purani), server offset {offset}")
        market_open = SessionBook.from_yaml(settings.sessions_path).market_open(now)
        if market_open and not 0 <= age <= 3:
            line(WARN, "Market khuli hai magar akhri candle ka waqt ajeeb hai — server offset check karein "
                       "(config mt5.server_utc_offset_hours)")
        feed.close()
        return 0
    except Exception as exc:  # noqa: BLE001
        line(FAIL, f"MT5: {exc}")
        return 1


def check_telegram(secrets) -> int:
    from trader_agent.notifier.telegram_sender import TelegramError, TelegramSender

    token, chat_id = secrets.get("TELEGRAM_BOT_TOKEN"), secrets.get("TELEGRAM_CHAT_ID")
    if not token:
        line(FAIL, "TELEGRAM_BOT_TOKEN khali hai")
        return 1
    try:
        me = TelegramSender(token, chat_id).whoami()
        line(OK, f"Telegram bot: @{me.get('username')}")
    except TelegramError as exc:
        line(FAIL, str(exc))
        return 1
    if not chat_id:
        line(WARN, "TELEGRAM_CHAT_ID khali — bot chala kar /start bhejein, woh ID batayega")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
