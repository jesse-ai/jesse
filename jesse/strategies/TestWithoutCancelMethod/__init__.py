from jesse.strategies import Strategy


class TestWithoutCancelMethod(Strategy):
    def should_long(self):
        return False

    def go_long(self):
        pass

    def go_short(self):
        pass

    def should_short(self):
        return False
