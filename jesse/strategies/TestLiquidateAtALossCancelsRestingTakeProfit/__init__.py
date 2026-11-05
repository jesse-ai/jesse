from jesse.enums import order_types
from jesse.store import store
from jesse.strategies import Strategy


class TestLiquidateAtALossCancelsRestingTakeProfit(Strategy):
    """
    The deterministic downtrend puts the position at a loss with both exits resting.
    On spot the take-profit holds the whole position, so the market sell can only be
    submitted once it is gone. Futures keep it until the position closes.
    """

    def should_long(self) -> bool:
        return self.index in (15, 40)

    def go_long(self) -> None:
        self.buy = 1, self.price

    def on_open_position(self, order) -> None:
        self.take_profit = 1, self.price + 20
        self.stop_loss = 1, self.price - 15

    def update_position(self) -> None:
        if self.index in (20, 45):
            take_profit_order = next(o for o in self.active_exit_orders if o.is_take_profit)
            self.liquidate()
            assert take_profit_order.is_canceled is self.is_spot_trading

    def on_close_position(self, order, closed_trade) -> None:
        assert order.type == order_types.MARKET
        assert order.is_stop_loss is True
        assert closed_trade.exit_price == self.price
        assert self.active_exit_orders == []

        if self.is_spot_trading:
            exchange = store.exchanges.get_exchange(self.exchange)
            assert exchange.assets['BTC'] == 0
            assert exchange.limit_orders_sum[self.symbol] == 0
            assert exchange.stop_orders_sum[self.symbol] == 0

    def before_terminate(self) -> None:
        assert len(self.trades) == 2
