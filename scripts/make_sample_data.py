"""Write SYNTHETIC random-walk M1 candles to try the tools before real data arrives.

Random data has no edge: any "result" on it is luck. Use it only to check that
backtest/replay run on your PC.

    python scripts/make_sample_data.py --days 20 --out data/history/SYNTHETIC_EURUSD_M1.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=20)
    parser.add_argument("--start", default="2026-01-05")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", default="data/history/SYNTHETIC_EURUSD_M1.csv")
    args = parser.parse_args()

    index = pd.date_range(args.start, periods=args.days * 1440, freq="1min", tz="UTC")
    index = index[index.day_of_week < 5]
    rng = np.random.default_rng(args.seed)
    close = 1.0850 + np.cumsum(rng.normal(0, 0.00012, len(index)))
    open_ = np.concatenate([[1.0850], close[:-1]])
    high = np.maximum(open_, close) + np.abs(rng.normal(0, 0.00008, len(index)))
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 0.00008, len(index)))
    frame = pd.DataFrame({"time": index.strftime("%Y-%m-%dT%H:%M:%SZ"), "open": open_, "high": high, "low": low, "close": close})
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.round(6).to_csv(out, index=False)
    print(f"SYNTHETIC data likha: {out} ({len(frame)} candles). Isay --format generic ke saath use karein.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
