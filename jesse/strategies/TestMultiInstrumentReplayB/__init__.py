from jesse.strategies import Strategy


# Shared with the paired BTC strategy's 2024-01-01 UTC fixture.
START = 1_704_067_200_000


class TestMultiInstrumentReplayB(Strategy):
    """Assert that sparse callbacks occur only when this instrument updates."""

    def before(self) -> None:
        expected_times = [START + 60_000, START + 180_000, START + 240_000]
        assert self.time == expected_times[self.index]
        assert self.get_candles(self.exchange, self.symbol, '1m')[-1, 0] == self.time - 60_000
        assert self.get_candles(self.exchange, 'BTC-USDT', '1m')[-1, 0] == self.time - 60_000

    def should_long(self) -> bool:
        return self.index == 0

    def go_long(self) -> None:
        # The missing ETH minute must not execute this stop against a stale candle.
        self.buy = 1, 101

    def should_cancel_entry(self) -> bool:
        return False

    def before_terminate(self) -> None:
        assert self.index == 3
