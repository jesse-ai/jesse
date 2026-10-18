import datetime as dt
from zoneinfo import ZoneInfo

from jesse.strategies import Strategy
from jesse import utils

# Runs on a 15m route over 1m candles from Fri 2026-03-06 00:00 UTC to Wed 2026-03-11 23:59 UTC
# (see tests/test_parent_strategy.py). US clocks moved forward on Sun 2026-03-08, so Friday's
# session opens at 09:00 UTC and Tuesday's at 08:00 UTC; Monday is a 'closed' holiday.
ET = ZoneInfo('America/New_York')
SCHEDULE = {
    'timezone': 'America/New_York',
    'hours': {'Mon-Fri': '04:00-20:00'},
    'closed': ['2026-03-09'],
}
SUB_WINDOW = {'timezone': 'America/New_York', 'hours': {'Mon-Fri': '16:00-20:00'}}
CANDLE_MS = 15 * 60_000

# Progress counters live at module level because Strategy._reset() clears self.vars.
_decisions = {}


def _et(timestamp: int) -> str:
    return dt.datetime.fromtimestamp(timestamp / 1000, ET).strftime('%Y-%m-%d %H:%M')


def _is_session_candle(open_time: int) -> bool:
    """Independent re-implementation of SCHEDULE for cross-checking the framework."""
    local = dt.datetime.fromtimestamp(open_time / 1000, ET)
    if local.weekday() > 4 or local.date() == dt.date(2026, 3, 9):
        return False
    return dt.time(4, 0) <= local.time() < dt.time(20, 0)


class TestTradingHoursCandleEdges(Strategy):
    def trading_hours(self):
        return SCHEDULE

    def before(self):
        if self.index == 0:
            _decisions.clear()

        # the helper is the open time of the candle that just closed, one candle before self.time
        open_time = self.closed_candle_open_time
        assert open_time == int(self.current_candle[0])
        assert open_time == int(self.candles[-1, 0])
        assert open_time == int(self.time) - CANDLE_MS

        assert self.is_trading_hours == _is_session_candle(open_time)
        # custom sub-windows keyed on the helper agree with filter_candles_by_hours
        assert utils.is_in_trading_hours(open_time, SUB_WINDOW) == bool(
            len(utils.filter_candles_by_hours(self.candles[-1:], SUB_WINDOW))
        )
        _decisions[_et(open_time)] = self.is_trading_hours

    def should_long(self):
        return False

    def should_short(self):
        return False

    def go_long(self):
        pass

    def go_short(self):
        pass

    def should_cancel_entry(self):
        return False

    def terminate(self):
        expected = {
            # Fri 2026-03-06 (EST, UTC-5)
            '2026-03-06 03:45': False,  # decided at 04:00: the night candle just closed
            '2026-03-06 04:00': True,   # decided at 04:15: first session candle
            '2026-03-06 19:45': True,   # decided at 20:00: last session candle
            '2026-03-06 20:00': False,  # decided at 20:15: first night candle
            # Mon 2026-03-09 is in 'closed'
            '2026-03-09 04:00': False,
            '2026-03-09 12:00': False,
            '2026-03-09 19:45': False,
            # Tue 2026-03-10 (EDT, UTC-4)
            '2026-03-10 03:45': False,
            '2026-03-10 04:00': True,
            '2026-03-10 19:45': True,
            '2026-03-10 20:00': False,
            # weekend
            '2026-03-07 12:00': False,
        }
        for local_open, in_session in expected.items():
            assert _decisions[local_open] is in_session, local_open
