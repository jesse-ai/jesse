import numpy as np

from jesse.strategies import Strategy


class TestClosedAnchorCandles(Strategy):
    def before(self):
        duration = 4 * 60 * 60_000
        closed = self.get_closed_candles(self.exchange, self.symbol, '4h')
        visible = self.get_candles(self.exchange, self.symbol, '4h')
        expected = visible[visible[:, 0] + duration <= self.time]
        np.testing.assert_array_equal(closed, expected)
        if len(closed):
            self.vars['saw_closed'] = True
            assert closed[-1, 0] + duration <= self.time
        if len(visible) > len(closed):
            self.vars['saw_forming'] = True

    def terminate(self):
        assert self.vars.get('saw_closed')
        assert self.vars.get('saw_forming')

    def should_long(self) -> bool:
        return False

    def should_short(self) -> bool:
        return False

    def should_cancel_entry(self) -> bool:
        return False

    def go_long(self):
        pass
