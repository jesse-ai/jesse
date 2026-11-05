from jesse.strategies import Strategy


class TestCannotOversellByReplacingTakeProfitInSpot(Strategy):
    """
    The replaced order must only be released once, so asking for twice the
    position has to be caught when the new take-profit orders are submitted.
    """

    def should_long(self) -> bool:
        return self.price == 10

    def go_long(self) -> None:
        self.buy = 1, self.price

    def on_open_position(self, order) -> None:
        self.take_profit = 1, 20

    def update_position(self) -> None:
        if self.price == 12:
            self.take_profit = [(1, 18), (1, 19)]
