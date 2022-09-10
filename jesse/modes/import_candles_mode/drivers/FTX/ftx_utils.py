from jesse.enums import timeframes


def timeframe_to_interval(timeframe: str) -> int:
    # 15, 60, 300, 900, 3600, 14400, 86400, or any multiple of 86400 up to 30*86400
    if timeframe == timeframes.MINUTE_1:
        return 60
    elif timeframe == timeframes.MINUTE_5:
        return 300
    elif timeframe == timeframes.MINUTE_15:
        return 900
    elif timeframe == timeframes.HOUR_1:
        return 3600
    elif timeframe == timeframes.HOUR_4:
        return 14400
    elif timeframe == timeframes.DAY_1:
        return 86400
    # elif timeframe == timeframes.WEEK_1:
    #     return 604800
    else:
        raise ValueError('Invalid timeframe: {}'.format(timeframe))


def interval_to_timeframe(interval: int) -> str:
    if interval == 60:
        return timeframes.MINUTE_1
    elif interval == 300:
        return timeframes.MINUTE_5
    elif interval == 900:
        return timeframes.MINUTE_15
    elif interval == 3600:
        return timeframes.HOUR_1
    elif interval == 14400:
        return timeframes.HOUR_4
    elif interval == 86400:
        return timeframes.DAY_1
    elif interval == 604800:
        return timeframes.WEEK_1
    else:
        raise ValueError('Invalid interval: {}'.format(interval))
