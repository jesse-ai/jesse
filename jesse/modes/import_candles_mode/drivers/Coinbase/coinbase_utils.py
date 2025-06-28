from jesse.enums import Timeframe


def timeframe_to_interval(timeframe: str) -> str:
    if timeframe == Timeframe.MINUTE_1.value:
        return 'ONE_MINUTE'
    elif timeframe == Timeframe.MINUTE_5.value:
        return 'FIVE_MINUTE'
    elif timeframe == Timeframe.MINUTE_15.value:
        return 'FIFTEEN_MINUTE'
    elif timeframe == Timeframe.MINUTE_30.value:
        return 'THIRTEEN_MINUTE'
    elif timeframe == Timeframe.HOUR_1.value:
        return 'ONE_HOUR'
    elif timeframe == Timeframe.HOUR_2.value:
        return 'TWO_HOUR'
    elif timeframe == Timeframe.HOUR_6.value:
        return 'SIX_HOUR'
    elif timeframe == Timeframe.DAY_1.value:
        return 'ONE_DAY'
    else:
        raise NotImplemented('Invalid timeframe: {}'.format(timeframe))


def interval_to_timeframe(interval: str) -> str:
    if interval == '60':
        return Timeframe.MINUTE_1.value
    else:
        raise NotImplemented('Invalid interval: {}'.format(interval))
