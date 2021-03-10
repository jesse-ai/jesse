from jesse.strategies import Strategy


class TestPositionWithLeverage2(Strategy):
    def should_long(self) -> bool:
        return self.price == 10

    def should_short(self) -> bool:
        return False

    def go_long(self):
        # price is at $1
        self.buy = 10, self.price

    def update_position(self):
        if self.price == 12:
            assert self.position.exchange.futures_leverage == 2
            assert self.position.pnl == 20
            assert self.position.total_cost == 50
            assert self.position.roi == 40
            assert self.position.pnl_percentage == self.position.roi

    def go_short(self):
        pass

    def should_cancel(self):
        return False
