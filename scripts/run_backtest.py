"""Backtest KSoR setups on historical M1 data and write an HTML + Markdown report.

Examples:
    python scripts/run_backtest.py --data data/history/DAT_ASCII_EURUSD_M1_2025.csv --pair EURUSD --include-drafts
    python scripts/run_backtest.py --data data/history/EURUSD_M1_2025.csv --pair EURUSD --oos-from 2025-10-01 --with-gate
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from trader_agent.backtest.engine import BacktestConfig, run_backtest  # noqa: E402
from trader_agent.backtest.report import build_report, write_report  # noqa: E402
from trader_agent.config import load_settings  # noqa: E402
from trader_agent.data_io import clean_candles, load_candles  # noqa: E402
from trader_agent.features import feature_names  # noqa: E402
from trader_agent.gate import RiskGate  # noqa: E402
from trader_agent.ksor import KsorError, load_risk_policy, load_setups  # noqa: E402
from trader_agent.news import load_events_csv  # noqa: E402
from trader_agent.timeutil import SessionBook  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", nargs="+", required=True, help="one or more CSV/ZIP files (same pair)")
    parser.add_argument("--format", default="histdata", choices=["histdata", "generic"])
    parser.add_argument("--tz", default="America/New_York", help="histdata file timezone (default: New York, with DST)")
    parser.add_argument("--tz-offset", type=float, help="force a fixed UTC offset for histdata files instead of --tz")
    parser.add_argument("--pair", required=True)
    parser.add_argument("--setup", action="append", help="only these setup ids (repeatable)")
    parser.add_argument("--include-drafts", action="store_true", help="also test draft setups")
    parser.add_argument("--payout", type=float, help="0.80 for 80%% (default: settings)")
    parser.add_argument("--from", dest="start", help="YYYY-MM-DD (UTC)")
    parser.add_argument("--to", dest="end", help="YYYY-MM-DD (UTC, exclusive)")
    parser.add_argument("--oos-from", help="YYYY-MM-DD: data after this is out-of-sample (verdict uses it)")
    parser.add_argument("--with-gate", action="store_true", help="simulate the risk gate (daily limits, cooldowns)")
    parser.add_argument("--events", help="news CSV (time_utc,currency,impact,title) for the gate")
    parser.add_argument("--synthetic", action="store_true", help="mark the report as synthetic test data")
    parser.add_argument("--out", help="report folder (default: settings reports dir)")
    args = parser.parse_args()

    settings = load_settings()
    sessions = SessionBook.from_yaml(settings.sessions_path)
    statuses = ("approved", "draft") if args.include_drafts else ("approved",)
    try:
        setups = load_setups(settings.setups_dir, statuses, feature_names(sessions), sessions.names())
    except KsorError as exc:
        print(exc)
        return 1
    if args.setup:
        wanted = {s.upper() for s in args.setup}
        setups = [s for s in setups if s.id in wanted]
    if not setups:
        print("Koi setup nahi mila. Draft setups ke liye --include-drafts lagayein.")
        return 1

    frames = [load_candles(path, args.format, args.tz_offset, args.tz) for path in args.data]
    candles, cleaning = clean_candles(pd.concat(frames))
    if args.start:
        candles = candles[candles.index >= pd.Timestamp(args.start, tz="UTC")]
    if args.end:
        candles = candles[candles.index < pd.Timestamp(args.end, tz="UTC")]
    if candles.empty:
        print("Is muddat mein koi candle nahi.")
        return 1
    print(f"Data: {len(candles)} candles ({candles.index[0]} → {candles.index[-1]}), cleaning: {cleaning}")

    config = BacktestConfig(
        payout=args.payout or settings.payout_default,
        use_gate=args.with_gate,
        oos_from=pd.Timestamp(args.oos_from, tz="UTC") if args.oos_from else None,
        display_tz=settings.display_timezone,
    )
    gate = None
    if args.with_gate:
        policy = load_risk_policy(settings.risk_policy_path, sessions.names())
        gate = RiskGate(policy, sessions, load_events_csv(args.events) if args.events else [])
    result = run_backtest(candles, args.pair, setups, sessions, config, gate)
    report = build_report(result, {"data": ", ".join(args.data), "synthetic": args.synthetic, "cleaning": cleaning})
    stem = f"backtest_{args.pair.upper()}_{pd.Timestamp.now(tz='UTC'):%Y%m%d_%H%M%S}"
    md_path, html_path = write_report(report, args.out or settings.reports_dir, stem)
    for section in report["sections"]:
        s = section["setup"]
        print(f"{s.id} v{s.version}: {section['verdict']} — {section['reason']}")
    print(f"Report: {html_path}\n        {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
