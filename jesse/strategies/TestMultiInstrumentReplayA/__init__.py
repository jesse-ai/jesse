from jesse.store import store
from jesse.strategies import Strategy


# 2024-01-01 00:00 UTC keeps every fixture bucket epoch-aligned.
START = 1_704_067_200_000


class TestMultiInstrumentReplayA(Strategy):
    """Assert atomic cross-symbol visibility and stale-instrument order isolation."""

    def before(self) -> None:
        expected_times = [
            START + 60_000,
            START + 120_000,
            START + 180_000,
            START + 240_000,
        ]
        assert self.time == expected_times[self.index]
        assert self.get_candles(self.exchange, self.symbol, '1m')[-1, 0] == self.time - 60_000

        eth_candles = self.get_candles(self.exchange, 'ETH-USDT', '1m')
        expected_eth_timestamp = START if self.index <= 1 else START + self.index * 60_000
        assert eth_candles[-1, 0] == expected_eth_timestamp

        eth_position = store.positions.get_position(self.exchange, 'ETH-USDT')
        if self.index == 1:
            # ETH has no source row at this event, so its pending stop cannot execute.
            assert eth_position.qty == 0
        elif self.index == 2:
            assert eth_position.qty == 1

    def should_long(self) -> bool:
        return False

    def go_long(self) -> None:
        pass

    def should_cancel_entry(self) -> bool:
        return False

    def before_terminate(self) -> None:
        assert self.index == 4
