"""Write the weekly review report (Markdown + HTML) from the SSoR database.

    python scripts/weekly_report.py              # last 7 days
    python scripts/weekly_report.py --days 30
"""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from trader_agent.config import load_settings  # noqa: E402
from trader_agent.ksor import KsorError, load_setups  # noqa: E402
from trader_agent.learning import weekly_report  # noqa: E402
from trader_agent.ssor import SSoR  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--db", help="SSoR file (default: settings)")
    args = parser.parse_args()
    settings = load_settings()
    try:
        setup_ids = [s.id for s in load_setups(settings.setups_dir)]
    except KsorError as exc:
        print(exc)
        return 1
    end = pd.Timestamp.now(tz="UTC")
    with SSoR(args.db or settings.db_path) as ssor:
        markdown = weekly_report(ssor, end - pd.Timedelta(days=args.days), end, settings.payout_default, setup_ids)
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    stem = settings.reports_dir / f"weekly_{end:%Y%m%d}"
    stem.with_suffix(".md").write_text(markdown, encoding="utf-8")
    body = html.escape(markdown)
    stem.with_suffix(".html").write_text(
        "<!doctype html><html><head><meta charset='utf-8'><title>Weekly report</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:900px;margin:24px auto;padding:0 16px;"
        "background:#fff;color:#1a1a1a}pre{white-space:pre-wrap;font:inherit}"
        "@media (prefers-color-scheme: dark){body{background:#151515;color:#e8e8e8}}</style></head>"
        f"<body><pre>{body}</pre></body></html>",
        encoding="utf-8",
    )
    print(markdown)
    print(f"Report: {stem.with_suffix('.html')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
