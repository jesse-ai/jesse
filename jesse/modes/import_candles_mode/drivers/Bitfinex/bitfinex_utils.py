from jesse.enums import timeframes


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
        return '1h'
    elif timeframe == timeframes.HOUR_3:
        return '3h'
    elif timeframe == timeframes.HOUR_6:
        return '6h'
    elif timeframe == timeframes.HOUR_12:
        return '12h'
    elif timeframe == timeframes.DAY_1:
        return '1D'
    elif timeframe == timeframes.WEEK_1:
        return '1W'
    elif timeframe == timeframes.MONTH_1:
        return '1M'
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
    elif interval == '1h':
        return timeframes.HOUR_1
    elif interval == '3h':
        return timeframes.HOUR_3
    elif interval == '6h':
        return timeframes.HOUR_6
    elif interval == '12h':
        return timeframes.HOUR_12
    elif interval == '1D':
        return timeframes.DAY_1
    elif interval == '1W':
        return timeframes.WEEK_1
    elif interval == '1M':
        return timeframes.MONTH_1
    else:
        raise NotImplemented('Invalid interval: {}'.format(interval))
