from jesse.strategies import Strategy


class TestDnaMethod(Strategy):
    def before(self):
        if self.index == 0:
            assert self.hp == {'profit_target': 7, 'qty_w': 86}

    def hyperparameters(self):
        return [
            {'name': 'qty_w', 'type': int, 'min': 10, 'max': 95, 'default': 70},
            {'name': 'profit_target', 'type': int, 'min': 1, 'max': 40, 'default': 5},
        ]

    def dna(self):
        return "o4"

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
