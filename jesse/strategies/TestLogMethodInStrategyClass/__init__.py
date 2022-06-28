from jesse.strategies import Strategy


class TestLogMethodInStrategyClass(Strategy):
    def before(self):
        if self.index == 10:
            self.log('test info log')

        if self.index == 11:
            self.log('test error log', log_type='error')

    def should_long(self) -> bool:
        return False

    def should_short(self) -> bool:
        return False

    def go_long(self):
        pass

    def go_short(self):
        pass

    def should_cancel_entry(self):
        return False
