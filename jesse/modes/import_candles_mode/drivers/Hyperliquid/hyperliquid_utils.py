from jesse.enums import Timeframe


def timeframe_to_interval(timeframe: str) -> str:
    """
    Convert a timeframe string to an interval in seconds.
    """
    if timeframe == Timeframe.MINUTE_1:
        return '1m'
    elif timeframe == Timeframe.MINUTE_3:
        return '3m'
    elif timeframe == Timeframe.MINUTE_5:
        return '5m'
    elif timeframe == Timeframe.MINUTE_15:
        return '15m'
    elif timeframe == Timeframe.MINUTE_30:
        return '30m'
    elif timeframe == Timeframe.HOUR_1:
        return '1h'
    elif timeframe == Timeframe.HOUR_2:
        return '2h'
    elif timeframe == Timeframe.HOUR_4:
        return '4h'
    elif timeframe == Timeframe.HOUR_6:
        return '6h'
    elif timeframe == Timeframe.HOUR_8:
        return '8h'
    elif timeframe == Timeframe.HOUR_12:
        return '12h'
    elif timeframe == Timeframe.DAY_1:
        return '1d'
    elif timeframe == Timeframe.DAY_3:
        return '3d'
    elif timeframe == Timeframe.WEEK_1:
        return '1w'
    else:
        raise ValueError('Invalid timeframe: {}'.format(timeframe))


def interval_to_timeframe(interval: str) -> str:
    """
    Convert an interval in seconds to a timeframe string.
    """
    if interval == '1':
        return Timeframe.MINUTE_1
    elif interval == '3':
        return Timeframe.MINUTE_3
    elif interval == '5':
        return Timeframe.MINUTE_5
    elif interval == '15':
        return Timeframe.MINUTE_15
    elif interval == '30':
        return Timeframe.MINUTE_30
    elif interval == '60':
        return Timeframe.HOUR_1
    elif interval == '120':
        return Timeframe.HOUR_2
    elif interval == '240':
        return Timeframe.HOUR_4
    elif interval == '360':
        return Timeframe.HOUR_6
    elif interval == '480':
        return Timeframe.HOUR_8
    elif interval == '720':
        return Timeframe.HOUR_12
    elif interval == 'D':
        return Timeframe.DAY_1
    elif interval == 'W':
        return Timeframe.WEEK_1
    else:
        raise ValueError('Invalid interval: {}'.format(interval))
