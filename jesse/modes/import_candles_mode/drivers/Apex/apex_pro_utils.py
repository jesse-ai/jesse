from jesse.enums import Timeframe


def timeframe_to_interval(timeframe: str) -> str:
    """
    Convert a timeframe string to an interval in seconds.
    """
    if timeframe == Timeframe.MINUTE_1.value:
        return '1'
    elif timeframe == Timeframe.MINUTE_3.value:
        return '3'
    elif timeframe == Timeframe.MINUTE_5.value:
        return '5'
    elif timeframe == Timeframe.MINUTE_15.value:
        return '15'
    elif timeframe == Timeframe.MINUTE_30.value:
        return '30'
    elif timeframe == Timeframe.HOUR_1.value:
        return '60'
    elif timeframe == Timeframe.HOUR_2.value:
        return '120'
    elif timeframe == Timeframe.HOUR_4.value:
        return '240'
    elif timeframe == Timeframe.HOUR_6.value:
        return '360'
    elif timeframe == Timeframe.HOUR_12.value:
        return '720'
    elif timeframe == Timeframe.DAY_1.value:
        return 'D'
    elif timeframe == Timeframe.WEEK_1.value:
        return 'W'
    else:
        raise ValueError('Invalid timeframe: {}'.format(timeframe))


def interval_to_timeframe(interval: str) -> str:
    """
    Convert an interval in seconds to a timeframe string.
    """
    if interval == '1':
        return Timeframe.MINUTE_1.value
    elif interval == '3':
        return Timeframe.MINUTE_3.value
    elif interval == '5':
        return Timeframe.MINUTE_5.value
    elif interval == '15':
        return Timeframe.MINUTE_15.value
    elif interval == '30':
        return Timeframe.MINUTE_30.value
    elif interval == '60':
        return Timeframe.HOUR_1.value
    elif interval == '120':
        return Timeframe.HOUR_2.value
    elif interval == '240':
        return Timeframe.HOUR_4.value
    elif interval == '360':
        return Timeframe.HOUR_6.value
    elif interval == '720':
        return Timeframe.HOUR_12.value
    elif interval == 'D':
        return Timeframe.DAY_1.value
    elif interval == 'W':
        return Timeframe.WEEK_1.value
    else:
        raise ValueError('Invalid interval: {}'.format(interval))
