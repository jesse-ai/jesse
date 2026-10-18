import numpy as np

from jesse.strategies import Strategy, cached
from jesse import utils

# The fake up-trend candles start on Thursday 2020-12-31 23:59 UTC and step one minute per
# candle, so a schedule with a single Friday window between 00:30 and 01:00 UTC lands in the
# middle of the run: some decisions fall inside it and most fall outside. A decision belongs to
# the candle that just closed, so it is judged by that candle's open time (self.time - 1m here).
SCHEDULE = {'timezone': 'UTC', 'hours': {'Fri': '00:30-01:00'}}
MINUTE_MS = 60_000
DAY_MS = 86_400_000

# Progress counters live at module level because Strategy._reset() clears self.vars.
_state = {'opened': 0, 'cancelled_at': None}


def _inside_window(timestamp: int) -> bool:
    """Independent re-implementation of the schedule for cross-checking the framework."""
    minute_of_day = (timestamp % DAY_MS) // MINUTE_MS
    weekday = (timestamp // DAY_MS + 3) % 7  # 1970-01-01 was a Thursday (Mon=0)
    return weekday == 4 and 30 <= minute_of_day < 60


class TestTradingHours(Strategy):
    def trading_hours(self):
        return SCHEDULE

    @property
    @cached
    def session_candles(self):
        return utils.filter_candles_by_hours(self.candles, self.trading_hours())

    def before(self):
        if self.index == 0:
            _state.update(opened=0, cancelled_at=None)

        # the just-closed candle, not self.time (its close), decides the gate
        assert self.closed_candle_open_time == int(self.current_candle[0])
        assert self.closed_candle_open_time == int(self.time) - MINUTE_MS
        assert self.is_trading_hours == _inside_window(self.closed_candle_open_time)

        candles = self.candles
        expected = candles[[_inside_window(int(t)) for t in candles[:, 0]]]
        assert np.array_equal(self.session_candles, expected)
        assert utils.filter_candles_by_hours(candles, None) is candles

    def should_long(self):
        # a market entry at 40 and a never-filling limit entry at 55, both inside the window
        return self.is_trading_hours and self.price in (40, 55)

    def should_short(self):
        return False

    def go_long(self):
        if self.price == 40:
            self.buy = 1, self.price
        else:
            self.buy = 1, self.price - 10

    def go_short(self):
        pass

    def on_open_position(self, order):
        assert self.is_trading_hours
        _state['opened'] += 1
        self.take_profit = 1, 42

    def should_cancel_entry(self):
        # Only asked while the limit entry is resting; the policy is "cancel once the window
        # closes". on_cancel() is not used for the check because the engine also fires it as
        # part of its post-close cleanup after the take-profit fills.
        cancel = not self.is_trading_hours
        if cancel:
            _state['cancelled_at'] = int(self.time)
        return cancel

    def terminate(self):
        assert _state['opened'] == 1
        assert self.trades_count == 1
        # the resting limit entry was cancelled once the first out-of-session candle (01:00-01:01)
        # had closed, i.e. at 01:01; under the old self.time rule it was cancelled at 01:00
        assert _state['cancelled_at'] is not None
        assert (_state['cancelled_at'] % DAY_MS) // MINUTE_MS == 61
