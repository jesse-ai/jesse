from jesse.store import store
from jesse.strategies import Strategy


# 2024-01-01 00:00 UTC is aligned for both fixture timeframes.
START = 1_704_067_200_000


class TestCommonWarmupStart(Strategy):
    """Assert that all routes trade only after the shared warmup boundary."""

    def before(self) -> None:
        assert store.app.starting_time == START + 30 * 60_000
        assert self.time == START + (35 + self.index * 5) * 60_000

        btc_five_minute = self.get_candles(self.exchange, 'BTC-USDT', '5m')
        eth_five_minute = self.get_candles(self.exchange, 'ETH-USDT', '5m')
        if self.index == 0:
            # BTC has extra warmup because its stream starts five minutes earlier.
            assert len(btc_five_minute) == 7
            assert len(eth_five_minute) == 6
            if self.symbol == 'BTC-USDT':
                assert len(store.candles.get_storage(self.exchange, 'BTC-USDT', '15m')) == 2

        assert btc_five_minute[-1, 0] == START + (30 + self.index * 5) * 60_000
        assert eth_five_minute[-1, 0] == START + (30 + self.index * 5) * 60_000
        assert btc_five_minute[-1, 5] == 4
        assert eth_five_minute[-1, 5] == 5

        # BTC has four then eight observable minutes in its 00:30 bucket, so
        # get_candles() must refresh the forming candle without filling either gap.
        btc_fifteen_minute = self.get_candles(self.exchange, 'BTC-USDT', '15m')
        assert btc_fifteen_minute[-1, 0] == START + 30 * 60_000
        assert btc_fifteen_minute[-1, 2] == 134 + self.index * 5
        assert btc_fifteen_minute[-1, 5] == 4 + self.index * 4

    def should_long(self) -> bool:
        return False

    def go_long(self) -> None:
        pass

    def should_cancel_entry(self) -> bool:
        return False

    def before_terminate(self) -> None:
        assert self.index == 2
