from jesse.strategies import Strategy


# test_inputs_get_rounded_behind_the_scene
class Test44(Strategy):
    def should_long(self) -> bool:
        return self.index == 2

    def should_short(self) -> bool:
        return False

    def go_long(self):
        self.buy = 1.54, 5.1234
        self.take_profit = 1.54, 10.1234
        self.stop_loss = 1.54, 1.1234

    def go_short(self):
        pass

    def should_cancel_entry(self):
        return False
