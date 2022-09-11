from jesse.enums import timeframes


def timeframe_to_interval(timeframe: str) -> str:
    if timeframe == timeframes.MINUTE_1:
        return '1min'
    elif timeframe == timeframes.MINUTE_5:
        return '5min'
    elif timeframe == timeframes.MINUTE_15:
        return '15min'
    elif timeframe == timeframes.MINUTE_30:
        return '30min'
    elif timeframe == timeframes.HOUR_1:
        return '1h'
    elif timeframe == timeframes.HOUR_4:
        return '4h'
    elif timeframe == timeframes.HOUR_6:
        return '6h'
    elif timeframe == timeframes.HOUR_12:
        return '12h'
    elif timeframe == timeframes.DAY_1:
        return '1day'


def interval_to_timeframe(interval: str) -> str:
    if interval == '1min':
        return timeframes.MINUTE_1
    elif interval == '5min':
        return timeframes.MINUTE_5
    elif interval == '15min':
        return timeframes.MINUTE_15
    elif interval == '30min':
        return timeframes.MINUTE_30
    elif interval == '1h':
        return timeframes.HOUR_1
    elif interval == '4h':
        return timeframes.HOUR_4
    elif interval == '6h':
        return timeframes.HOUR_6
    elif interval == '12h':
        return timeframes.HOUR_12
    elif interval == '1day':
        return timeframes.DAY_1
