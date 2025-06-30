from jesse.enums import timeframes


CANDLE_SOURCE_MAPPING = {
    "open":    lambda c: c[:, 1],
    "close":   lambda c: c[:, 2],
    "high":    lambda c: c[:, 3],
    "low":     lambda c: c[:, 4],
    "volume":  lambda c: c[:, 5],
    "hl2":     lambda c: (c[:, 3] + c[:, 4]) / 2,
    "hlc3":    lambda c: (c[:, 3] + c[:, 4] + c[:, 2]) / 3,
    "ohlc4":   lambda c: (c[:, 1] + c[:, 3] + c[:, 4] + c[:, 2]) / 4,
}


TIMEFRAME_PRIORITY = [
    timeframes.DAY_1,
    timeframes.HOUR_12,
    timeframes.HOUR_8,
    timeframes.HOUR_6,
    timeframes.HOUR_4,
    timeframes.HOUR_3,
    timeframes.HOUR_2,
    timeframes.HOUR_1,
    timeframes.MINUTE_45,
    timeframes.MINUTE_30,
    timeframes.MINUTE_15,
    timeframes.MINUTE_5,
    timeframes.MINUTE_3,
    timeframes.MINUTE_1,
]


TIMEFRAME_TO_ONE_MINUTES = {
    timeframes.MINUTE_1: 1,
    timeframes.MINUTE_3: 3,
    timeframes.MINUTE_5: 5,
    timeframes.MINUTE_15: 15,
    timeframes.MINUTE_30: 30,
    timeframes.MINUTE_45: 45,
    timeframes.HOUR_1: 60,
    timeframes.HOUR_2: 60 * 2,
    timeframes.HOUR_3: 60 * 3,
    timeframes.HOUR_4: 60 * 4,
    timeframes.HOUR_6: 60 * 6,
    timeframes.HOUR_8: 60 * 8,
    timeframes.HOUR_12: 60 * 12,
    timeframes.DAY_1: 60 * 24,
    timeframes.DAY_3: 60 * 24 * 3,
    timeframes.WEEK_1: 60 * 24 * 7,
    timeframes.MONTH_1: 60 * 24 * 30,
}


SUPPORTED_COLORS = {
    'black',
    'red',
    'green',
    'yellow',
    'blue',
    'magenta',
    'cyan',
    'white',
    #'gray',
}