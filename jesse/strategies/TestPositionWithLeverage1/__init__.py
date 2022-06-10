from jesse.strategies import Strategy


class TestPositionWithLeverage1(Strategy):
    def should_long(self) -> bool:
        return self.index == 0

    def should_short(self) -> bool:
        return False

    def go_long(self):
        # price is at $1
        self.buy = 10, self.price

    def update_position(self):
        if self.price == 3:
            assert self.position.pnl == 20
            assert self.position.roi == 200
            assert self.position.total_cost == 10

    def go_short(self):
        pass

    def should_cancel_entry(self):
        return False
