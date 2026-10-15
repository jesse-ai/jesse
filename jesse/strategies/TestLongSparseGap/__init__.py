import numpy as np

from jesse.store import store
from jesse.strategies import Strategy


# 2024-01-01 00:00 UTC is aligned to the fixture's 5m buckets.
START = 1_704_067_200_000


class TestLongSparseGap(Strategy):
    """Assert that a long source gap omits empty buckets without shifting later ones."""

    def before(self) -> None:
        assert self.index == 0
        assert self.time == START + 15 * 60_000

        five_minute = self.get_candles(self.exchange, self.symbol, '5m')
        assert len(five_minute) == 2
        np.testing.assert_array_equal(
            five_minute[0],
            np.array([START, 10, 11, 12, 9, 1], dtype=np.float64),
        )
        # Minutes 05 through 09 are entirely empty. Minute 14 remains in its
        # clock-aligned 00:10 bucket rather than shifting beside minute 00.
        np.testing.assert_array_equal(
            five_minute[1],
            np.array([START + 10 * 60_000, 24, 25, 26, 23, 15], dtype=np.float64),
        )

    def should_long(self) -> bool:
        return False

    def go_long(self) -> None:
        pass

    def should_cancel_entry(self) -> bool:
        return False

    def before_terminate(self) -> None:
        assert self.index == 1
        assert store.app.time == START + 15 * 60_000
