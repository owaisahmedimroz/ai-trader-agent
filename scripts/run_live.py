"""Run the agent live on this PC (Windows + MT5 terminal open).

    python scripts/run_live.py                      # approved setups -> Telegram signals
    python scripts/run_live.py --shadow-drafts      # + draft setups recorded silently (champion/challenger)
    python scripts/run_live.py --shadow-only        # plumbing test before Ustad's rules: drafts as SHADOW signals

The agent only signals; you place trades yourself. Stop with Ctrl+C.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from trader_agent.config import brain_models, load_secrets, load_settings  # noqa: E402
from trader_agent.ksor import KsorError  # noqa: E402
from trader_agent.live import LiveRunner  # noqa: E402
from trader_agent.notifier.console import ConsoleNotifier, MultiNotifier  # noqa: E402
from trader_agent.pipeline import Agent, NullNotifier  # noqa: E402


def build_brain(settings, secrets, ssor):
    """(confirmer, briefer, reviewer) or Nones when the brain is off or not configured."""
    cfg = settings.brain
    models = brain_models(secrets)
    if not cfg["enabled"]:
        return None, None, None
    if "ANTHROPIC_API_KEY" not in secrets or not models:
        print("⚠️  brain.enabled hai magar ANTHROPIC_API_KEY ya BRAIN_MODEL_* .env mein nahi — AI band rahega.")
        return None, None, None
    from trader_agent.brain.client import BrainClient
    from trader_agent.brain.confirm import Confirmer
    from trader_agent.brain.review import ai_briefing, nightly_review

    client = BrainClient(ssor, models, int(cfg["max_calls_per_day"]), int(cfg["max_tokens_per_day"]))
    effort = cfg["effort"]
    confirmer = Confirmer(client, cfg["on_unavailable"], float(cfg["confirm_timeout_seconds"]), effort["confirm"]) if "fast" in models else None

    def briefer(facts):
        import pandas as pd

        return ai_briefing(client, facts, pd.Timestamp.now(tz="UTC"), effort["briefing"]) if "balanced" in models else None

    def reviewer(start, end, now):
        if "deep" not in models:
            return {"summary": "BRAIN_MODEL_DEEP set nahi — review skip.", "reflections": 0, "proposals": 0}
        return nightly_review(client, ssor, start, end, now, int(settings.learning["proposal_min_evidence"]), effort["review"])

    return confirmer, briefer, reviewer


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--shadow-drafts", action="store_true", help="also run draft setups silently (recorded as shadow)")
    parser.add_argument("--shadow-only", action="store_true", help="only drafts, as visible SHADOW test signals")
    parser.add_argument("--no-telegram", action="store_true", help="terminal only")
    parser.add_argument("--max-ticks", type=int, help="stop after N candles (testing)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = load_settings()
    secrets = load_secrets()
    if settings.feed != "mt5":
        print("config/settings.yaml mein feed: mt5 karein (live ke liye MT5 chahiye).")
        return 1
    missing = [k for k in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER") if k not in secrets]
    if missing:
        print(f".env mein {missing} chahiye.")
        return 1

    notifier = ConsoleNotifier(settings.display_timezone)
    if not args.no_telegram and secrets.get("TELEGRAM_BOT_TOKEN") and secrets.get("TELEGRAM_CHAT_ID"):
        from trader_agent.notifier.telegram_sender import TelegramSender

        notifier = MultiNotifier(
            notifier,
            TelegramSender(secrets["TELEGRAM_BOT_TOKEN"], secrets["TELEGRAM_CHAT_ID"], settings.display_timezone),
            on_error=lambda channel, exc: logging.warning("notify failed via %s: %s", type(channel).__name__, exc),
        )
    elif not args.no_telegram:
        print("⚠️  Telegram token/chat ID nahi mile — signals sirf terminal mein dikhenge.")

    try:
        if args.shadow_only:
            agents = [Agent.from_settings(settings, notifier, mode="shadow", statuses=("draft", "approved"),
                                          control_path=settings.control_path)]
        else:
            live = Agent.from_settings(settings, notifier, mode="live", control_path=settings.control_path)
            if not live.setups:
                print("Koi approved setup nahi. Pehle Ustad ke setups approve karein, ya --shadow-only se test karein.")
                return 1
            agents = [live]
            if args.shadow_drafts:
                agents.append(Agent.from_settings(settings, NullNotifier(), mode="shadow", statuses=("draft",),
                                                  control_path=settings.control_path))
    except (KsorError, ValueError) as exc:
        print(exc)
        return 1

    confirmer, briefer, reviewer = build_brain(settings, secrets, agents[0].ssor)
    for agent in agents:
        if agent.mode == "live":
            agent.brain = confirmer

    calendar_loader = None
    if settings.calendar["enabled"] and settings.calendar["url"]:
        from trader_agent.calendar_feed import fetch_calendar

        def load_calendar():
            return fetch_calendar(settings.calendar["url"], settings.data_dir / "calendar_cache.json",
                                  float(settings.calendar["refresh_hours"]))

        calendar_loader = load_calendar

    from trader_agent.feeds.mt5_feed import MT5Feed

    feed = MT5Feed(secrets["MT5_LOGIN"], secrets["MT5_PASSWORD"], secrets["MT5_SERVER"],
                   settings.mt5_symbols, settings.mt5_server_utc_offset_hours)
    runner = LiveRunner(agents, feed, notifier, briefer=briefer, reviewer=reviewer, calendar_loader=calendar_loader)
    print("Live loop shuru. Band karne ke liye Ctrl+C.")
    try:
        runner.run(max_ticks=args.max_ticks)
    except KeyboardInterrupt:
        notifier.send_text("⏹ Agent band kar diya gaya.")
    finally:
        feed.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
