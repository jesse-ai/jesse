from jesse.strategies import Strategy


class TestOrdersAreSortedBeforeExecution(Strategy):
    def should_long(self):
        return self.price == 10

    def go_long(self):
        self.buy = [
            (1, 10.2),
            (1, 10.3),
            (1, 10.1)
        ]

    def on_open_position(self, order) -> None:
        # the order with the lowest price should be executed first
        assert order.price == 10.1

    def update_position(self):
        if self.price == 20:
            self.liquidate()

    def should_cancel_entry(self):
        return False
