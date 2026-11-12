"""Load and clean historical M1 candles (for backtests and replays).

Supported formats:
- histdata: HistData.com "Generic ASCII" M1 files, lines like
  `20250102 000000;1.035030;1.035100;1.034980;1.035060;0`. HistData documents
  its timestamps as EST without daylight saving, but the 2024–2026 files were
  checked against US NFP releases (08:30 New York) and weekly opens (Sunday
  17:00 New York): they are New York local time WITH daylight saving. So the
  default timezone is America/New_York; `tz_offset_hours` forces a fixed offset.
- generic: CSV with a header `time,open,high,low,close[,volume]`; `time` in UTC
  (ISO text) unless a timezone is given.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

COLUMNS = ["open", "high", "low", "close"]


def load_histdata_m1(path: Path | str, tz: str = "America/New_York", tz_offset_hours: float | None = None) -> pd.DataFrame:
    raw = pd.read_csv(
        path,
        sep=";",
        header=None,
        names=["stamp", "open", "high", "low", "close", "volume"],
        dtype={"stamp": str},
    )
    naive = pd.to_datetime(raw["stamp"].str.strip(), format="%Y%m%d %H%M%S")
    if tz_offset_hours is not None:
        utc = (naive - pd.Timedelta(hours=tz_offset_hours)).dt.tz_localize("UTC")
    else:  # DST switches happen early Sunday when forex is closed, so nothing should be ambiguous
        utc = naive.dt.tz_localize(tz, ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
    frame = raw[COLUMNS + ["volume"]].astype("float64")
    frame.index = pd.DatetimeIndex(utc, name="time")
    return frame[frame.index.notna()]


def load_generic_csv(path: Path | str, time_column: str = "time", tz: str = "UTC") -> pd.DataFrame:
    raw = pd.read_csv(path)
    missing = [c for c in [time_column, *COLUMNS] if c not in raw.columns]
    if missing:
        raise ValueError(f"{path}: missing columns {missing}")
    stamps = pd.to_datetime(raw[time_column])
    stamps = stamps.dt.tz_localize(tz) if stamps.dt.tz is None else stamps
    keep = COLUMNS + (["volume"] if "volume" in raw.columns else [])
    frame = raw[keep].astype("float64")
    frame.index = pd.DatetimeIndex(stamps.dt.tz_convert("UTC"), name="time")
    return frame


def load_candles(path: Path | str, fmt: str = "histdata", tz_offset_hours: float | None = None,
                 tz: str = "America/New_York") -> pd.DataFrame:
    if fmt == "histdata":
        return load_histdata_m1(path, tz, tz_offset_hours)
    if fmt == "generic":
        return load_generic_csv(path)
    raise ValueError(f"unknown format {fmt!r} (use histdata or generic)")


def clean_candles(candles: pd.DataFrame, spike_pct: float = 2.0) -> tuple[pd.DataFrame, dict]:
    """Sort, drop duplicates/broken rows and single-candle spikes. Returns (clean, report)."""
    report = {"rows_in": len(candles)}
    df = candles.sort_index()
    duplicated = df.index.duplicated(keep="last")
    report["duplicates"] = int(duplicated.sum())
    df = df[~duplicated]
    prices = df[COLUMNS]
    broken = prices.isna().any(axis=1) | (prices <= 0).any(axis=1) | (df["high"] < df[["open", "close"]].max(axis=1)) | (
        df["low"] > df[["open", "close"]].min(axis=1)
    )
    report["broken_rows"] = int(broken.sum())
    df = df[~broken]
    jump = (df["close"] / df["close"].shift(1) - 1).abs() * 100
    back = (df["close"].shift(-1) / df["close"] - 1).abs() * 100
    spikes = (jump > spike_pct) & (back > spike_pct)  # jumps away and straight back
    report["spikes"] = int(spikes.sum())
    df = df[~spikes]
    gaps = df.index.to_series().diff()
    weekday_gaps = gaps[(gaps > pd.Timedelta(minutes=1)) & (gaps < pd.Timedelta(hours=2))]
    report["small_gaps"] = int(len(weekday_gaps))
    report["missing_minutes_in_small_gaps"] = int(
        np.sum((weekday_gaps / pd.Timedelta(minutes=1)).to_numpy() - 1) if len(weekday_gaps) else 0
    )
    report["rows_out"] = len(df)
    if len(df):
        report["first"], report["last"] = str(df.index[0]), str(df.index[-1])
    return df, report
