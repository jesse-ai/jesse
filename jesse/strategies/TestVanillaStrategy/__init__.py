from jesse.strategies import Strategy


class TestVanillaStrategy(Strategy):
    def should_long(self):
        return False

    def go_long(self):
        pass

    def should_cancel(self):
        return False
