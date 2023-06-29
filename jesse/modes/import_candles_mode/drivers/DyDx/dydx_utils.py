from jesse.enums import timeframes


def timeframe_to_interval(timeframe: str) -> str:
    # 1DAY, 4HOURS, 1HOUR, 30MINS, 15MINS, 5MINS, 1MIN
    if timeframe == timeframes.MINUTE_1:
        return '1MIN'
    elif timeframe == timeframes.MINUTE_5:
        return '5MINS'
    elif timeframe == timeframes.MINUTE_15:
        return '15MINS'
    elif timeframe == timeframes.MINUTE_30:
        return '30MINS'
    elif timeframe == timeframes.HOUR_1:
        return '1HOUR'
    elif timeframe == timeframes.HOUR_4:
        return '4HOURS'
    elif timeframe == timeframes.DAY_1:
        return '1DAY'
    else:
        raise ValueError('Invalid timeframe: {}'.format(timeframe))
