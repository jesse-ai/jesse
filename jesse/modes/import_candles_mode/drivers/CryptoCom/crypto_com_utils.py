from jesse.enums import timeframes


def timeframe_to_interval(timeframe: str) -> str:
    # 1m
    # 5m
    # 15m
    # 30m
    # 1h
    # 2h
    # 4h
    # 12h
    # 1d
    # 1w
    # 1M
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
    elif timeframe == timeframes.HOUR_2:
        return '2h'
    elif timeframe == timeframes.HOUR_4:
        return '4h'
    elif timeframe == timeframes.HOUR_12:
        return '12h'
    elif timeframe == timeframes.DAY_1:
        return '1d'
    elif timeframe == timeframes.WEEK_1:
        return '7D'
    elif timeframe == timeframes.MONTH_1:
        return '1M'
    else:
        raise ValueError('Invalid timeframe: {}'.format(timeframe))


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
    elif interval == '2h':
        return timeframes.HOUR_2
    elif interval == '4h':
        return timeframes.HOUR_4
    elif interval == '12h':
        return timeframes.HOUR_12
    elif interval == '1d':
        return timeframes.DAY_1
    elif interval == '7D':
        return timeframes.WEEK_1
    elif interval == '1M':
        return timeframes.MONTH_1
    else:
        raise ValueError('Invalid interval: {}'.format(interval))
