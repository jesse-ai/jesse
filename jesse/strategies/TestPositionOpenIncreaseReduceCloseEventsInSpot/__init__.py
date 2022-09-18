from jesse.strategies import Strategy
import jesse.helpers as jh
from jesse import utils


class TestPositionOpenIncreaseReduceCloseEventsInSpot(Strategy):
    def before(self) -> None:
        if self.index == 0:
            self.vars['called_on_open_position'] = False
            self.vars['called_on_increased_position'] = False
            self.vars['called_on_reduced_position'] = False
            self.vars['called_on_close_position'] = False

    def before_terminate(self):
        assert self.vars['called_on_open_position'] is True
        assert self.vars['called_on_increased_position'] is True
        assert self.vars['called_on_reduced_position'] is True
        assert self.vars['called_on_close_position'] is True

    def should_long(self):
        return self.price == 10

    def go_long(self):
        self.buy = [
            (1, 10),
            (2, 12)
        ]

    def on_open_position(self, order) -> None:
        assert order.qty == 1
        assert self.position.qty == 0.999
        self.vars['called_on_open_position'] = True

    def on_increased_position(self, order) -> None:
        assert order.qty == 2
        assert self.position.qty == 2.997
        self.vars['called_on_increased_position'] = True

        # submit reduce and closing orders
        self.take_profit = [
            (0.999, 15),
            (1.998, 17),
        ]

    def on_reduced_position(self, order) -> None:
        assert order.qty == -0.999
        assert self.position.qty == 1.998
        self.vars['called_on_reduced_position'] = True

    def on_close_position(self, order) -> None:
        assert order.qty == -1.998
        assert self.position.qty == 0
        self.vars['called_on_close_position'] = True

    def should_cancel_entry(self):
        return False
