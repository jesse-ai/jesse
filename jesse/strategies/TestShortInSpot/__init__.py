from jesse.strategies import Strategy


class TestShortInSpot(Strategy):
    def should_short(self) -> bool:
        return True

    def go_short(self) -> None:
        self.sell = 1, self.price

    def should_long(self):
        return False

    def go_long(self):
        pass

    def should_cancel_entry(self):
        return False


