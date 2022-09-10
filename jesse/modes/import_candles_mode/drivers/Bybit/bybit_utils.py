from jesse.enums import timeframes


def timeframe_to_interval(timeframe: str) -> str:
    """
    Convert a timeframe string to an interval in seconds.
    """
    if timeframe == timeframes.MINUTE_1:
        return '1'
    elif timeframe == timeframes.MINUTE_3:
        return '3'
    elif timeframe == timeframes.MINUTE_5:
        return '5'
    elif timeframe == timeframes.MINUTE_15:
        return '15'
    elif timeframe == timeframes.MINUTE_30:
        return '30'
    elif timeframe == timeframes.HOUR_1:
        return '60'
    elif timeframe == timeframes.HOUR_2:
        return '120'
    elif timeframe == timeframes.HOUR_4:
        return '240'
    elif timeframe == timeframes.HOUR_6:
        return '360'
    elif timeframe == timeframes.HOUR_12:
        return '720'
    elif timeframe == timeframes.DAY_1:
        return 'D'
    elif timeframe == timeframes.WEEK_1:
        return 'W'
    else:
        raise ValueError('Invalid timeframe: {}'.format(timeframe))


def interval_to_timeframe(interval: str) -> str:
    """
    Convert an interval in seconds to a timeframe string.
    """
    if interval == '1':
        return timeframes.MINUTE_1
    elif interval == '3':
        return timeframes.MINUTE_3
    elif interval == '5':
        return timeframes.MINUTE_5
    elif interval == '15':
        return timeframes.MINUTE_15
    elif interval == '30':
        return timeframes.MINUTE_30
    elif interval == '60':
        return timeframes.HOUR_1
    elif interval == '120':
        return timeframes.HOUR_2
    elif interval == '240':
        return timeframes.HOUR_4
    elif interval == '360':
        return timeframes.HOUR_6
    elif interval == '720':
        return timeframes.HOUR_12
    elif interval == 'D':
        return timeframes.DAY_1
    elif interval == 'W':
        return timeframes.WEEK_1
    else:
        raise ValueError('Invalid interval: {}'.format(interval))
