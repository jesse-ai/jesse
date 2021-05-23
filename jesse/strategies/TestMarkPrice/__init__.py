from jesse.strategies import Strategy


class TestMarkPrice(Strategy):
    def before(self):
        if self.index < 10:
            assert self.price == self.mark_price
            assert self.funding_rate == 0
            assert self.next_funding_timestamp is None

    def should_long(self) -> bool:
        return False

    def should_short(self) -> bool:
        return False

    def go_long(self):
        pass

    def go_short(self):
        pass

    def should_cancel(self):
        return False
