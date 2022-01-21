from jesse.strategies import Strategy


class TestEmptyStrategy(Strategy):
    def should_long(self):
        return False

    def should_short(self):
        return False

    def should_cancel(self):
        return False

    def go_long(self):
        pass

    def go_short(self):
        pass
