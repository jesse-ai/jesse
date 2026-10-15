import numpy as np

from jesse.store import store
from jesse.strategies import Strategy


# 2024-01-01 00:00 UTC is aligned for both fixture timeframes.
START = 1_704_067_200_000


class TestSparseTimestampRoutes(Strategy):
    """Assert clock-bucket timing and same-event data-route visibility."""

    def before(self) -> None:
        assert self.time == START + 900_000
        assert self.index == 0

        five_minute = self.get_candles(self.exchange, self.symbol, '5m')
        assert len(five_minute) == 2
        # The nonempty 00:00 bucket closed during the ten-minute source gap,
        # while the completely empty 00:05 bucket must not be manufactured.
        np.testing.assert_array_equal(
            five_minute[0],
            np.array([START, 10, 12, 13, 9, 3], dtype=np.float64),
        )
        np.testing.assert_array_equal(
            five_minute[1],
            np.array([START + 600_000, 22, 25, 26, 21, 28], dtype=np.float64),
        )

        fifteen_minute = self.get_candles(self.exchange, self.symbol, '15m')
        assert len(fifteen_minute) == 1
        # The completed data route must be installed before the 5m strategy
        # callback that shares its 00:15 availability timestamp.
        np.testing.assert_array_equal(
            fifteen_minute[-1],
            np.array([START, 10, 25, 26, 9, 31], dtype=np.float64),
        )

    def should_long(self) -> bool:
        return False

    def go_long(self) -> None:
        pass

    def should_cancel_entry(self) -> bool:
        return False

    def before_terminate(self) -> None:
        assert self.index == 1
        assert store.app.time == START + 900_000
