from jesse.store import store
from jesse.strategies import Strategy


class TestSpotSellOrderSumsFollowRestingOrders(Strategy):
    """
    The oversell check relies on these sums matching what is actually resting: one
    per exit while a position is open, even after both exits were replaced, and zero
    once the trade is closed and its sibling exit got canceled.
    """

    def should_long(self) -> bool:
        return self.index in (15, 40)

    def go_long(self) -> None:
        self.buy = 1, self.price

    def on_open_position(self, order) -> None:
        self.take_profit = 1, self.price + 10
        self.stop_loss = 1, self.price - 10

    def update_position(self) -> None:
        if self.index in (17, 42):
            self.take_profit = 1, self.price + 5
            self.stop_loss = 1, self.price - 5

    def after(self) -> None:
        exchange = store.exchanges.get_exchange(self.exchange)
        expected_sum = 1 if self.position.is_open else 0
        assert exchange.limit_orders_sum.get(self.symbol, 0) == expected_sum
        assert exchange.stop_orders_sum.get(self.symbol, 0) == expected_sum

    def before_terminate(self) -> None:
        assert len(self.trades) == 2
