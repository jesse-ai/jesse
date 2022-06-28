from jesse.strategies import Strategy


# test_fee_rate_property
class Test48(Strategy):
    def should_long(self) -> bool:
        # default fee for unit tests is set to 0, so:
        assert self.fee_rate == 0
        return False

    def should_short(self) -> bool:
        # default fee for unit tests is set to 0, so:
        assert self.fee_rate == 0
        return False

    def go_long(self):
        pass

    def go_short(self):
        pass

    def should_cancel_entry(self):
        return False
