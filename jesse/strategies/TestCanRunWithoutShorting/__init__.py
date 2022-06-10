from jesse.strategies import Strategy


class TestCanRunWithoutShorting(Strategy):
    def should_long(self):
        return False

    def should_cancel_entry(self):
        return False

    def go_long(self):
        pass
