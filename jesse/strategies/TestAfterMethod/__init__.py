from jesse.strategies import Strategy


# test_after
class TestAfterMethod(Strategy):
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

    def before(self):
        if self.index == 1:
            assert self.vars['counter'] == 100

    def after(self):
        if self.index == 0:
            self.vars['counter'] = 100
