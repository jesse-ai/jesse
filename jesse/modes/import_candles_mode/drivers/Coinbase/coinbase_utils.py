from jesse.enums import timeframes


def timeframe_to_interval(timeframe: str) -> str:
    if timeframe == timeframes.MINUTE_1:
        return 'ONE_MINUTE'
    elif timeframe == timeframes.MINUTE_5:
        return 'FIVE_MINUTE'
    elif timeframe == timeframes.MINUTE_15:
        return 'FIFTEEN_MINUTE'
    elif timeframe == timeframes.MINUTE_30:
        return 'THIRTEEN_MINUTE'
    elif timeframe == timeframes.HOUR_1:
        return 'ONE_HOUR'
    elif timeframe == timeframes.HOUR_2:
        return 'TWO_HOUR'
    elif timeframe == timeframes.HOUR_6:
        return 'SIX_HOUR'
    elif timeframe == timeframes.DAY_1:
        return 'ONE_DAY'
    else:
        raise NotImplemented('Invalid timeframe: {}'.format(timeframe))


def interval_to_timeframe(interval: str) -> str:
    if interval == '60':
        return timeframes.MINUTE_1
    else:
        raise NotImplemented('Invalid interval: {}'.format(interval))
