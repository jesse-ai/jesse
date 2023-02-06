from jesse.enums import timeframes
import jesse.helpers as jh


def timeframe_to_interval(timeframe: str) -> str:
    if timeframe == timeframes.MINUTE_1:
        return '1m'
    elif timeframe == timeframes.MINUTE_5:
        return '5m'
    elif timeframe == timeframes.MINUTE_15:
        return '15m'
    elif timeframe == timeframes.MINUTE_30:
        return '30m'
    elif timeframe == timeframes.HOUR_1:
        return '1H'
    elif timeframe == timeframes.HOUR_4:
        return '4H'
    elif timeframe == timeframes.HOUR_12:
        return '12H'
    elif timeframe == timeframes.DAY_1:
        return '1D'
    else:
        raise NotImplemented('Invalid timeframe: {}'.format(timeframe))


def interval_to_timeframe(interval: str) -> str:
    if interval == '1m':
        return timeframes.MINUTE_1
    elif interval == '5m':
        return timeframes.MINUTE_5
    elif interval == '15m':
        return timeframes.MINUTE_15
    elif interval == '30m':
        return timeframes.MINUTE_30
    elif interval == '1H':
        return timeframes.HOUR_1
    elif interval == '4H':
        return timeframes.HOUR_4
    elif interval == '12H':
        return timeframes.HOUR_12
    elif interval == '1D':
        return timeframes.DAY_1
    else:
        raise NotImplemented('Invalid interval: {}'.format(interval))
