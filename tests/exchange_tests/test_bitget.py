from jesse.modes.import_candles_mode.drivers.Bitget import bitget_utils
from jesse.enums import timeframes


def test_timeframe_to_interval():
    assert bitget_utils.timeframe_to_interval(timeframes.MINUTE_1) == '1m'
    assert bitget_utils.timeframe_to_interval(timeframes.MINUTE_5) == '5m'
    assert bitget_utils.timeframe_to_interval(timeframes.MINUTE_15) == '15m'
    assert bitget_utils.timeframe_to_interval(timeframes.MINUTE_30) == '30m'
    assert bitget_utils.timeframe_to_interval(timeframes.HOUR_1) == '1H'
    assert bitget_utils.timeframe_to_interval(timeframes.HOUR_4) == '4H'
    assert bitget_utils.timeframe_to_interval(timeframes.HOUR_12) == '12H'
    assert bitget_utils.timeframe_to_interval(timeframes.DAY_1) == '1D'


def test_interval_to_timeframe():
    assert bitget_utils.interval_to_timeframe('1m') == timeframes.MINUTE_1
    assert bitget_utils.interval_to_timeframe('5m') == timeframes.MINUTE_5
    assert bitget_utils.interval_to_timeframe('15m') == timeframes.MINUTE_15
    assert bitget_utils.interval_to_timeframe('30m') == timeframes.MINUTE_30
    assert bitget_utils.interval_to_timeframe('1H') == timeframes.HOUR_1
    assert bitget_utils.interval_to_timeframe('4H') == timeframes.HOUR_4
    assert bitget_utils.interval_to_timeframe('12H') == timeframes.HOUR_12
    assert bitget_utils.interval_to_timeframe('1D') == timeframes.DAY_1
