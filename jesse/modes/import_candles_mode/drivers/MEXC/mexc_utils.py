from jesse.enums import timeframes


def timeframe_to_interval(timeframe: str) -> str:
    # 1m
    # 5m
    # 15m
    # 30m
    # 1h
    # 2h
    # 4h
    # 6h
    # 8h
    # 1d
    if timeframe == timeframes.MINUTE_1:
        return 'Min1'
    elif timeframe == timeframes.MINUTE_5:
        return 'Min5'
    elif timeframe == timeframes.MINUTE_15:
        return 'Min15'
    elif timeframe == timeframes.MINUTE_30:
        return 'Min30'
    elif timeframe == timeframes.HOUR_1:
        return 'Min60'
    elif timeframe == timeframes.HOUR_4:
        return 'Hour4'
    elif timeframe == timeframes.HOUR_8:
        return 'Hour8'
    elif timeframe == timeframes.DAY_1:
        return 'Day1'
    else:
        raise ValueError('Invalid timeframe: {}'.format(timeframe))


def interval_to_timeframe(interval: str) -> str:
    if interval == 'Min1':
        return timeframes.MINUTE_1
    elif interval == 'Min4':
        return timeframes.MINUTE_5
    elif interval == 'Min15':
        return timeframes.MINUTE_15
    elif interval == 'Min30':
        return timeframes.MINUTE_30
    elif interval == 'Min60':
        return timeframes.HOUR_1
    elif interval == 'Hour4':
        return timeframes.HOUR_4
    elif interval == 'Hour8':
        return timeframes.HOUR_8
    elif interval == 'Day1':
        return timeframes.DAY_1
    else:
        raise ValueError('Invalid interval: {}'.format(interval))
