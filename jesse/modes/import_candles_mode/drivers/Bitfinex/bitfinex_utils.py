from jesse.enums import Timeframe


def timeframe_to_interval(timeframe: str) -> str:
    if timeframe == Timeframe.MINUTE_1:
        return '1m'
    elif timeframe == Timeframe.MINUTE_5:
        return '5m'
    elif timeframe == Timeframe.MINUTE_15:
        return '15m'
    elif timeframe == Timeframe.MINUTE_30:
        return '30m'
    elif timeframe == Timeframe.HOUR_1:
        return '1h'
    elif timeframe == Timeframe.HOUR_3:
        return '3h'
    elif timeframe == Timeframe.HOUR_6:
        return '6h'
    elif timeframe == Timeframe.HOUR_12:
        return '12h'
    elif timeframe == Timeframe.DAY_1:
        return '1D'
    elif timeframe == Timeframe.WEEK_1:
        return '1W'
    elif timeframe == Timeframe.MONTH_1:
        return '1M'
    else:
        raise NotImplemented('Invalid timeframe: {}'.format(timeframe))


def interval_to_timeframe(interval: str) -> str:
    if interval == '1m':
        return Timeframe.MINUTE_1
    elif interval == '5m':
        return Timeframe.MINUTE_5
    elif interval == '15m':
        return Timeframe.MINUTE_15
    elif interval == '30m':
        return Timeframe.MINUTE_30
    elif interval == '1h':
        return Timeframe.HOUR_1
    elif interval == '3h':
        return Timeframe.HOUR_3
    elif interval == '6h':
        return Timeframe.HOUR_6
    elif interval == '12h':
        return Timeframe.HOUR_12
    elif interval == '1D':
        return Timeframe.DAY_1
    elif interval == '1W':
        return Timeframe.WEEK_1
    elif interval == '1M':
        return Timeframe.MONTH_1
    else:
        raise NotImplemented('Invalid interval: {}'.format(interval))
