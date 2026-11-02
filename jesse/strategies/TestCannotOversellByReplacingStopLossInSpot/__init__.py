from jesse.strategies import Strategy


class TestCannotOversellByReplacingStopLossInSpot(Strategy):
    """
    The replaced order must only be released once, so asking for twice the
    position has to be caught when the new stop-loss orders are submitted.
    """

    def should_long(self) -> bool:
        return self.price == 10

    def go_long(self) -> None:
        self.buy = 1, self.price

    def on_open_position(self, order) -> None:
        self.stop_loss = 1, 5

    def update_position(self) -> None:
        if self.price == 12:
            self.stop_loss = [(1, 8), (1, 9)]
