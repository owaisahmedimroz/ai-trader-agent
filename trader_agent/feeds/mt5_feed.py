"""MetaTrader 5 price feed (Windows only) — data only, never trades.

Status: written in Phase 1 but NOT yet verified on a real MT5 terminal. Phase 2
must check it on Windows (`python scripts/check_setup.py --mt5`), especially:

- MT5 returns candle times in the broker's *server* time (often UTC+2/+3), not
  UTC. We estimate the offset from the latest tick, or use
  `mt5.server_utc_offset_hours` from config/settings.yaml when set.
- Symbol names differ between brokers (EURUSD vs EURUSDm): `mt5.symbols` maps them.
"""

from __future__ import annotations

import pandas as pd

from .base import Feed


class MT5Feed(Feed):
    def __init__(self, login: str, password: str, server: str, symbols: dict[str, str] | None = None,
                 server_utc_offset_hours: float | None = None):
        try:
            import MetaTrader5 as mt5
        except ImportError as exc:
            raise RuntimeError(
                "MetaTrader5 package nahi mila. Yeh sirf Windows par chalta hai: pip install MetaTrader5"
            ) from exc
        self.mt5 = mt5
        if not mt5.initialize(login=int(login), password=password, server=server):
            raise RuntimeError(f"MT5 se connect nahi ho saka: {mt5.last_error()} (MT5 terminal khula hai?)")
        self.symbols = {k.upper(): v for k, v in (symbols or {}).items()}
        self._offset = None if server_utc_offset_hours is None else pd.Timedelta(hours=server_utc_offset_hours)

    def symbol(self, pair: str) -> str:
        name = self.symbols.get(pair.upper(), pair.upper())
        if not self.mt5.symbol_select(name, True):
            raise RuntimeError(f"MT5 mein symbol {name!r} nahi mila — config mt5.symbols check karein")
        return name

    def server_offset(self, pair: str) -> pd.Timedelta:
        """Broker server time minus UTC, rounded to the hour (needs a fresh tick)."""
        if self._offset is not None:
            return self._offset
        tick = self.mt5.symbol_info_tick(self.symbol(pair))
        if tick is None:
            raise RuntimeError("MT5 se tick nahi mila (market band ho sakti hai) — server_utc_offset_hours set karein")
        server_now = pd.Timestamp(tick.time, unit="s", tz="UTC")
        hours = round((server_now - pd.Timestamp.now(tz="UTC")).total_seconds() / 3600)
        self._offset = pd.Timedelta(hours=hours)
        return self._offset

    def candles(self, pair: str, count: int) -> pd.DataFrame:
        name = self.symbol(pair)
        # start_pos=1 skips the candle that is still forming (position 0)
        rates = self.mt5.copy_rates_from_pos(name, self.mt5.TIMEFRAME_M1, 1, count)
        if rates is None or len(rates) == 0:
            raise RuntimeError(f"MT5 se {name} ki candles nahi mili: {self.mt5.last_error()}")
        frame = pd.DataFrame(rates)
        times = pd.to_datetime(frame["time"], unit="s", utc=True) - self.server_offset(pair)
        out = frame[["open", "high", "low", "close"]].astype("float64")
        out["volume"] = frame["tick_volume"].astype("float64")
        out.index = pd.DatetimeIndex(times, name="time")
        return out

    def lag_seconds(self, pair: str) -> float | None:
        tick = self.mt5.symbol_info_tick(self.symbol(pair))
        if tick is None:
            return None
        tick_utc = pd.Timestamp(tick.time, unit="s", tz="UTC") - self.server_offset(pair)
        return (pd.Timestamp.now(tz="UTC") - tick_utc).total_seconds()

    def close(self) -> None:
        self.mt5.shutdown()
