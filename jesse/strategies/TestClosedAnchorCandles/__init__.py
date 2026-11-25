import numpy as np

from jesse.strategies import Strategy
from jesse.services import candle_service


class TestClosedAnchorCandles(Strategy):
    def before(self):
        duration = 4 * 60 * 60_000
        closed = self.get_candles(self.exchange, self.symbol, '4h')
        current = candle_service.get_current_candle(self.exchange, self.symbol, '4h')
        assert np.all(closed[:, 0] + duration <= self.time)
        # Fixture source prices increase by one every minute, starting at UTC midnight.
        expected_count = (self.time - 1_704_153_600_000) // duration
        assert len(closed) == expected_count
        if len(closed):
            self.vars['saw_closed'] = True
            assert closed[-1, 2] == expected_count * 240
        if len(current) and current[0] + duration > self.time:
            self.vars['saw_forming'] = True
            assert not len(closed) or closed[-1, 0] < current[0]

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
