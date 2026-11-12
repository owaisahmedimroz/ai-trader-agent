import pandas as pd
import pytest

from trader_agent.data_io import clean_candles, load_candles


def test_histdata_lines_are_new_york_time_with_dst(tmp_path):
    """Checked on the real 2024–2026 files: the NFP spike sits at 08:30 file time in winter AND summer."""
    path = tmp_path / "DAT_ASCII_EURUSD_M1_2025.csv"
    path.write_text(
        "20250110 083000;1.030000;1.036000;1.029000;1.035000;0\n"  # NFP, winter (EST)
        "20250703 083000;1.178000;1.179000;1.171000;1.172000;0\n",  # NFP, summer (EDT)
        encoding="utf-8",
    )
    candles = load_candles(path, "histdata")
    assert candles.index[0] == pd.Timestamp("2025-01-10 13:30", tz="UTC")
    assert candles.index[1] == pd.Timestamp("2025-07-03 12:30", tz="UTC")
    assert candles["close"].iloc[1] == pytest.approx(1.172)
    fixed = load_candles(path, "histdata", tz_offset_hours=-5)  # the documented-but-wrong reading
    assert fixed.index[1] == pd.Timestamp("2025-07-03 13:30", tz="UTC")


def test_generic_csv(tmp_path):
    path = tmp_path / "eurusd.csv"
    path.write_text("time,open,high,low,close\n2026-01-05T00:00:00Z,1.1,1.2,1.0,1.15\n", encoding="utf-8")
    candles = load_candles(path, "generic")
    assert str(candles.index.tz) == "UTC" and candles["high"].iloc[0] == 1.2


def test_cleaning_removes_duplicates_broken_rows_and_spikes():
    index = pd.date_range("2026-01-05", periods=8, freq="1min", tz="UTC")
    frame = pd.DataFrame(
        {
            "open": [1.10, 1.10, 1.10, 1.10, 1.10, 1.10, 1.10, 1.10],
            "high": [1.11, 1.11, 1.11, 1.11, 1.11, 1.11, 1.11, 1.11],
            "low": [1.09, 1.09, 1.09, 1.12, 1.09, 1.09, 1.09, 1.09],  # row 3: low > open (broken)
            "close": [1.10, 1.10, 1.10, 1.10, 1.10, 1.30, 1.10, 1.10],  # row 5: one-candle spike
        },
        index=index,
    )
    frame.loc[index[5], "high"] = 1.31
    duplicated = pd.concat([frame, frame.iloc[[0]]]).sort_index()
    clean, report = clean_candles(duplicated)
    assert report["duplicates"] == 1 and report["broken_rows"] == 1 and report["spikes"] == 1
    assert len(clean) == 6
    assert report["small_gaps"] >= 1


def test_unknown_format():
    with pytest.raises(ValueError):
        load_candles("x.csv", "excel")
