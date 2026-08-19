from jesse.enums import order_types
from jesse.store import store
from jesse.strategies import Strategy


class TestGeneratedDataRouteExecutionBTC(Strategy):
    """Trade the one-minute BTC route while consuming its generated 5m data route."""

    def should_long(self) -> bool:
        # BTC closes begin at 101, so index 9 gives an exact market entry at 110.
        return self.index == 9

    def go_long(self) -> None:
        self.buy = 1, self.price

    def on_open_position(self, order) -> None:
        assert order.type == order_types.MARKET
        assert order.price == 110
        self.take_profit = 1, 120

    def on_close_position(self, order, closed_trade) -> None:
        assert order.type == order_types.LIMIT
        assert closed_trade.symbol == 'BTC-USDT'
        assert closed_trade.timeframe == '1m'
        assert closed_trade.entry_price == 110
        assert closed_trade.exit_price == 120
        assert closed_trade.qty == 1

    def before_terminate(self) -> None:
        five_minute_candles = self.get_candles(self.exchange, self.symbol, '5m')

        # The 99 underlying candles produce ceil(99 / 5) aggregates. Checking
        # OHLC values proves that the data route contains generated market data,
        # not merely the correct route metadata.
        assert len(five_minute_candles) == 20
        assert five_minute_candles[0][1:5].tolist() == [100.5, 105, 105, 100.5]
        assert five_minute_candles[-1][2] == 199

        assert len(store.closed_trades.trades) == 2
        assert store.app.total_open_trades == 0
        assert store.app.total_liquidations == 0
        exchange = store.exchanges.get_exchange(self.exchange)
        # Both routes earn 10 with zero configured fees against one shared wallet.
        assert exchange.wallet_balance == 10_020
