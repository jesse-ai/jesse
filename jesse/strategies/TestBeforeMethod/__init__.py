from jesse.strategies import Strategy


# test_before
class TestBeforeMethod(Strategy):
    def should_long(self) -> bool:
        if self.index == 0:
            assert self.vars['counter'] == 10

        elif self.index == 2:
            assert self.vars['counter'] == 100

        return False

    def should_short(self) -> bool:
        return False

    def go_long(self):
        pass

    def go_short(self):
        pass

    def should_cancel_entry(self):
        return False

    def before(self):
        if self.index == 0:
            self.vars['counter'] = 10

        elif self.index == 2:
            self.vars['counter'] = 100
