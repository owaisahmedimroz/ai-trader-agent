"""The interface every price feed implements."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class Feed(ABC):
    @abstractmethod
    def candles(self, pair: str, count: int) -> pd.DataFrame:
        """The last `count` CLOSED M1 candles, oldest first, UTC DatetimeIndex (candle open time)."""

    def candles_with_forming(self, pair: str, count: int) -> pd.DataFrame:
        """Closed candles plus the still-forming one as the last row (for the heads-up)."""
        raise NotImplementedError

    def lag_seconds(self, pair: str) -> float | None:
        """How old the latest price is, if the feed knows."""
        return None

    def close(self) -> None:
        pass
