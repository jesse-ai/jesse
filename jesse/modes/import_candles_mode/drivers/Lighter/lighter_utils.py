from jesse.enums import timeframes

# Lighter candle resolutions <-> Jesse timeframes.
# Lighter also serves '1w', but Jesse has no 1-week timeframe so it is intentionally omitted.
TIMEFRAME_TO_RESOLUTION = {
    timeframes.MINUTE_1: '1m',
    timeframes.MINUTE_5: '5m',
    timeframes.MINUTE_15: '15m',
    timeframes.MINUTE_30: '30m',
    timeframes.HOUR_1: '1h',
    timeframes.HOUR_4: '4h',
    timeframes.HOUR_12: '12h',
    timeframes.DAY_1: '1d',
}

RESOLUTION_TO_TIMEFRAME = {v: k for k, v in TIMEFRAME_TO_RESOLUTION.items()}


def timeframe_to_resolution(timeframe: str) -> str:
    try:
        return TIMEFRAME_TO_RESOLUTION[timeframe]
    except KeyError:
        raise ValueError(f'Timeframe "{timeframe}" is not supported by the Lighter driver')


def resolution_to_timeframe(resolution: str) -> str:
    try:
        return RESOLUTION_TO_TIMEFRAME[resolution]
    except KeyError:
        raise ValueError(f'Resolution "{resolution}" is not a supported Lighter resolution')
