from jesse.store import store
from jesse.strategies import Strategy


class TestSplitExitsWithinRoundingErrorOfBalanceInSpot(Strategy):
    """
    With this qty and a 0.1% fee, three equal parts add up to 3.696300000000001 while
    3.6963000000000004 is held. That is a rounding error rather than an oversell, so
    both exits have to be accepted, and execution still caps the sells at the balance.
    """

    def should_long(self) -> bool:
        return self.price == 10

    def go_long(self) -> None:
        self.buy = 3.7, self.price

    def on_open_position(self, order) -> None:
        part = self.position.qty / 3
        self.take_profit = [(part, 15), (part, 16), (part, 17)]
        self.stop_loss = [(part, 8), (part, 7), (part, 6)]

    def on_close_position(self, order, closed_trade) -> None:
        exchange = store.exchanges.get_exchange(self.exchange)
        assert closed_trade.exit_price > 15
        assert exchange.assets['BTC'] == 0
        self.vars['closed'] = True

    def before_terminate(self) -> None:
        assert self.vars['closed'] is True
