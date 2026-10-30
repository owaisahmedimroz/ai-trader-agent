"""Replay history candle by candle through the real agent pipeline (a live-like dry run).

Signals print in the terminal; with --telegram they also go to your phone with
buttons (run the bot in another window and use the same --db so presses are saved).

Examples:
    python scripts/replay.py --data data/history/EURUSD_M1_2025.csv --pair EURUSD --from 2025-03-03 --to 2025-03-04 --include-drafts
    python scripts/replay.py ... --telegram --sleep 3 --db data/ssor.sqlite3
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from trader_agent.config import load_secrets, load_settings  # noqa: E402
from trader_agent.data_io import clean_candles, load_candles  # noqa: E402
from trader_agent.ksor import KsorError  # noqa: E402
from trader_agent.notifier.console import ConsoleNotifier, MultiNotifier  # noqa: E402
from trader_agent.notifier.messages import format_day_summary  # noqa: E402
from trader_agent.notifier.telegram_bot import control_path  # noqa: E402
from trader_agent.pipeline import Agent  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", nargs="+", required=True)
    parser.add_argument("--format", default="histdata", choices=["histdata", "generic"])
    parser.add_argument("--tz-offset", type=float, default=-5.0)
    parser.add_argument("--pair", required=True)
    parser.add_argument("--from", dest="start", required=True, help="YYYY-MM-DD (UTC)")
    parser.add_argument("--to", dest="end", required=True, help="YYYY-MM-DD (UTC, exclusive)")
    parser.add_argument("--include-drafts", action="store_true")
    parser.add_argument("--db", help="SSoR file (default: a new data/replay_<time>.sqlite3)")
    parser.add_argument("--telegram", action="store_true", help="also send signals to Telegram")
    parser.add_argument("--sleep", type=float, default=0.0, help="seconds to wait after each signal")
    args = parser.parse_args()

    settings = load_settings()
    db_path = Path(args.db) if args.db else settings.db_path.parent / f"replay_{pd.Timestamp.now():%Y%m%d_%H%M%S}.sqlite3"
    notifier = ConsoleNotifier(settings.display_timezone)
    if args.telegram:
        from trader_agent.notifier.telegram_sender import TelegramSender

        secrets = load_secrets()
        notifier = MultiNotifier(
            notifier,
            TelegramSender(secrets.get("TELEGRAM_BOT_TOKEN", ""), secrets.get("TELEGRAM_CHAT_ID", ""), settings.display_timezone),
        )
    try:
        agent = Agent.from_settings(
            settings, notifier, mode="replay", include_drafts=args.include_drafts,
            db_path=db_path, control_path=control_path(settings),
        )
    except (KsorError, ValueError) as exc:
        print(exc)
        return 1
    if not agent.setups:
        print("Koi setup nahi. Draft setups ke liye --include-drafts lagayein.")
        return 1

    candles, _ = clean_candles(pd.concat([load_candles(p, args.format, args.tz_offset) for p in args.data]))
    start, end = pd.Timestamp(args.start, tz="UTC"), pd.Timestamp(args.end, tz="UTC")
    timeline = candles.index[(candles.index >= start) & (candles.index < end)]
    if timeline.empty:
        print("Is muddat mein koi candle nahi.")
        return 1
    print(f"Replay {args.pair.upper()} {timeline[0]} → {timeline[-1]} ({len(timeline)} candles), SSoR: {db_path}")
    lookback = settings.lookback_bars
    positions = candles.index.get_indexer(timeline)
    total = 0
    for pos in positions:
        window = candles.iloc[max(0, pos - lookback + 1) : pos + 1]
        new_ids = agent.on_closed_candle(args.pair, window)
        total += len(new_ids)
        if new_ids and args.sleep:
            time.sleep(args.sleep)
    agent.resolve_outcomes(args.pair, candles)
    summary = agent.ssor.day_summary(start, end + pd.Timedelta(minutes=30), mode="replay")
    print("\n" + format_day_summary(summary, title=f"Replay {args.start} → {args.end}"))
    print(f"Signals: {total}. Decisions log aur signals SSoR mein: {db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
