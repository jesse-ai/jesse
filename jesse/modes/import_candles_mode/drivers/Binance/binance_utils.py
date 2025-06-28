from jesse.enums import Timeframe


def timeframe_to_interval(timeframe: str) -> str:
    # 1m
    # 3m
    # 5m
    # 15m
    # 30m
    # 1h
    # 2h
    # 4h
    # 6h
    # 8h
    # 12h
    # 1d
    # 3d
    # 1w
    # 1M
    if timeframe == Timeframe.MINUTE_1.value:
        return '1m'
    elif timeframe == Timeframe.MINUTE_3.value:
        return '3m'
    elif timeframe == Timeframe.MINUTE_5.value:
        return '5m'
    elif timeframe == Timeframe.MINUTE_15.value:
        return '15m'
    elif timeframe == Timeframe.MINUTE_30.value:
        return '30m'
    elif timeframe == Timeframe.HOUR_1.value:
        return '1h'
    elif timeframe == Timeframe.HOUR_2.value:
        return '2h'
    elif timeframe == Timeframe.HOUR_4.value:
        return '4h'
    elif timeframe == Timeframe.HOUR_6.value:
        return '6h'
    elif timeframe == Timeframe.HOUR_8.value:
        return '8h'
    elif timeframe == Timeframe.HOUR_12.value:
        return '12h'
    elif timeframe == Timeframe.DAY_1.value:
        return '1d'
    elif timeframe == Timeframe.DAY_3.value:
        return '3d'
    elif timeframe == Timeframe.WEEK_1.value:
        return '1w'
    elif timeframe == Timeframe.MONTH_1.value:
        return '1M'
    else:
        raise ValueError('Invalid timeframe: {}'.format(timeframe))


def interval_to_timeframe(interval: str) -> str:
    if interval == '1m':
        return Timeframe.MINUTE_1.value
    elif interval == '3m':
        return Timeframe.MINUTE_3.value
    elif interval == '5m':
        return Timeframe.MINUTE_5.value
    elif interval == '15m':
        return Timeframe.MINUTE_15.value
    elif interval == '30m':
        return Timeframe.MINUTE_30.value
    elif interval == '1h':
        return Timeframe.HOUR_1.value
    elif interval == '2h':
        return Timeframe.HOUR_2.value
    elif interval == '4h':
        return Timeframe.HOUR_4.value
    elif interval == '6h':
        return Timeframe.HOUR_6.value
    elif interval == '8h':
        return Timeframe.HOUR_8.value
    elif interval == '12h':
        return Timeframe.HOUR_12.value
    elif interval == '1d':
        return Timeframe.DAY_1.value
    elif interval == '3d':
        return Timeframe.DAY_3.value
    elif interval == '1w':
        return Timeframe.WEEK_1.value
    elif interval == '1M':
        return Timeframe.MONTH_1.value
    else:
        raise ValueError('Invalid interval: {}'.format(interval))
