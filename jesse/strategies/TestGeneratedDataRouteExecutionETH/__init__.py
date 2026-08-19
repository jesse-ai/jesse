from jesse.enums import order_types
from jesse.store import store
from jesse.strategies import Strategy


class TestGeneratedDataRouteExecutionETH(Strategy):
    """Trade the generated 5m ETH route while consuming its generated 15m data route."""

    def should_long(self) -> bool:
        # Generated 5m closes are 5, 10, 15, ...; index 1 must therefore be 10.
        return self.index == 1

    def go_long(self) -> None:
        assert self.price == 10
        self.buy = 1, self.price

    def on_open_position(self, order) -> None:
        assert order.type == order_types.MARKET
        self.take_profit = 1, 20

    def on_close_position(self, order, closed_trade) -> None:
        assert order.type == order_types.LIMIT
        assert closed_trade.symbol == 'ETH-USDT'
        assert closed_trade.timeframe == '5m'
        assert closed_trade.entry_price == 10
        assert closed_trade.exit_price == 20
        assert closed_trade.qty == 1

    def before_terminate(self) -> None:
        fifteen_minute_candles = self.get_candles(self.exchange, self.symbol, '15m')

        # The 99 underlying candles produce ceil(99 / 15) aggregates. Checking
        # OHLC values also proves that ETH's data stayed isolated from BTC.
        assert len(fifteen_minute_candles) == 7
        assert fifteen_minute_candles[0][1:5].tolist() == [0.5, 15, 15, 0.5]
        assert fifteen_minute_candles[-1][2] == 99

        assert len(store.closed_trades.trades) == 2
        assert store.app.total_open_trades == 0
        assert store.app.total_liquidations == 0
        exchange = store.exchanges.get_exchange(self.exchange)
        # Both routes earn 10 with zero configured fees against one shared wallet.
        assert exchange.wallet_balance == 10_020
