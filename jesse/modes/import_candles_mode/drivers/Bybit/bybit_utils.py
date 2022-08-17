def timeframe_to_interval(timeframe: str) -> str:
    """
    Convert a timeframe string to an interval in seconds.
    """
    if timeframe == '1m':
        return '1'
    elif timeframe == '3m':
        return '3'
    elif timeframe == '5m':
        return '5'
    elif timeframe == '15m':
        return '15'
    elif timeframe == '30m':
        return '30'
    elif timeframe == '1h':
        return '60'
    elif timeframe == '2h':
        return '120'
    elif timeframe == '4h':
        return '240'
    elif timeframe == '6h':
        return '360'
    elif timeframe == '12h':
        return '720'
    elif timeframe == '1D':
        return 'D'
    elif timeframe == '1W':
        return 'W'
    else:
        raise ValueError('Invalid timeframe: {}'.format(timeframe))


def interval_to_timeframe(interval: str) -> str:
    """
    Convert an interval in seconds to a timeframe string.
    """
    if interval == '1':
        return '1m'
    elif interval == '3':
        return '3m'
    elif interval == '5':
        return '5m'
    elif interval == '15':
        return '15m'
    elif interval == '30':
        return '30m'
    elif interval == '60':
        return '1h'
    elif interval == '120':
        return '2h'
    elif interval == '240':
        return '4h'
    elif interval == '360':
        return '6h'
    elif interval == '720':
        return '12h'
    elif interval == 'D':
        return '1D'
    elif interval == 'W':
        return '1W'
    else:
        raise ValueError('Invalid interval: {}'.format(interval))

