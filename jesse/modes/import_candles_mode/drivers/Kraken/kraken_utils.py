from jesse.enums import timeframes


# Kraken interval values are in MINUTES (for both Spot OHLC and the Futures charts API
# resolution names below). Spot OHLC accepts: 1, 5, 15, 30, 60, 240, 1440, 10080, 21600.
def timeframe_to_interval(timeframe: str) -> str:
    mapping = {
        timeframes.MINUTE_1: '1',
        timeframes.MINUTE_5: '5',
        timeframes.MINUTE_15: '15',
        timeframes.MINUTE_30: '30',
        timeframes.HOUR_1: '60',
        timeframes.HOUR_4: '240',
        timeframes.DAY_1: '1440',
    }
    if timeframe not in mapping:
        raise ValueError(f'Invalid timeframe: {timeframe}')
    return mapping[timeframe]


def interval_to_timeframe(interval: str) -> str:
    mapping = {
        '1': timeframes.MINUTE_1,
        '5': timeframes.MINUTE_5,
        '15': timeframes.MINUTE_15,
        '30': timeframes.MINUTE_30,
        '60': timeframes.HOUR_1,
        '240': timeframes.HOUR_4,
        '1440': timeframes.DAY_1,
    }
    if str(interval) not in mapping:
        raise ValueError(f'Invalid interval: {interval}')
    return mapping[str(interval)]


# The Kraken Futures charts API uses string resolution names instead of minute integers.
def timeframe_to_futures_resolution(timeframe: str) -> str:
    mapping = {
        timeframes.MINUTE_1: '1m',
        timeframes.MINUTE_5: '5m',
        timeframes.MINUTE_15: '15m',
        timeframes.MINUTE_30: '30m',
        timeframes.HOUR_1: '1h',
        timeframes.HOUR_4: '4h',
        timeframes.DAY_1: '1d',
    }
    if timeframe not in mapping:
        raise ValueError(f'Invalid timeframe: {timeframe}')
    return mapping[timeframe]
