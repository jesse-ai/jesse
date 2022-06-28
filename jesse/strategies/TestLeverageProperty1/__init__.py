from jesse.strategies import Strategy


# test_leverage_property
class TestLeverageProperty1(Strategy):
    def should_long(self) -> bool:
        if self.index == 0:
            assert self.leverage == 1

        return False

    def should_short(self) -> bool:
        return False

    def go_long(self):
        pass

    def go_short(self):
        pass

    def should_cancel_entry(self):
        return False
