from jesse.strategies import Strategy


class TestOptimizationIsolation(Strategy):
    """Generate enough deterministic trades for multi-process research tests."""

    def hyperparameters(self) -> list:
        return [
            {'name': 'entry_interval', 'type': int, 'min': 4, 'max': 5, 'default': 4},
        ]

    def should_long(self) -> bool:
        return self.index % self.hp['entry_interval'] == 0

    def go_long(self) -> None:
        self.buy = 1, self.price

    def should_cancel_entry(self) -> bool:
        return False

    def on_open_position(self, order) -> None:
        self.take_profit = self.position.qty, self.price + 1
