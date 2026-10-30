import pandas as pd
import pytest

from trader_agent.data_io import clean_candles, load_candles


def test_histdata_lines_are_shifted_to_utc(tmp_path):
    path = tmp_path / "DAT_ASCII_EURUSD_M1_2025.csv"
    path.write_text(
        "20250102 000000;1.035030;1.035100;1.034980;1.035060;0\n"
        "20250102 000100;1.035060;1.035200;1.035000;1.035150;0\n",
        encoding="utf-8",
    )
    candles = load_candles(path, "histdata")
    assert candles.index[0] == pd.Timestamp("2025-01-02 05:00", tz="UTC")  # EST (UTC-5) -> UTC
    assert candles["close"].iloc[1] == pytest.approx(1.03515)


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
