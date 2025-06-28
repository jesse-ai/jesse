from jesse.enums import Timeframe


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
    Timeframe.DAY_1.value,
    Timeframe.HOUR_12.value,
    Timeframe.HOUR_8.value,
    Timeframe.HOUR_6.value,
    Timeframe.HOUR_4.value,
    Timeframe.HOUR_3.value,
    Timeframe.HOUR_2.value,
    Timeframe.HOUR_1.value,
    Timeframe.MINUTE_45.value,
    Timeframe.MINUTE_30.value,
    Timeframe.MINUTE_15.value,
    Timeframe.MINUTE_5.value,
    Timeframe.MINUTE_3.value,
    Timeframe.MINUTE_1.value,
]


TIMEFRAME_TO_ONE_MINUTES = {
    Timeframe.MINUTE_1.value: 1,
    Timeframe.MINUTE_3.value: 3,
    Timeframe.MINUTE_5.value: 5,
    Timeframe.MINUTE_15.value: 15,
    Timeframe.MINUTE_30.value: 30,
    Timeframe.MINUTE_45.value: 45,
    Timeframe.HOUR_1.value: 60,
    Timeframe.HOUR_2.value: 60 * 2,
    Timeframe.HOUR_3.value: 60 * 3,
    Timeframe.HOUR_4.value: 60 * 4,
    Timeframe.HOUR_6.value: 60 * 6,
    Timeframe.HOUR_8.value: 60 * 8,
    Timeframe.HOUR_12.value: 60 * 12,
    Timeframe.DAY_1.value: 60 * 24,
    Timeframe.DAY_3.value: 60 * 24 * 3,
    Timeframe.WEEK_1.value: 60 * 24 * 7,
    Timeframe.MONTH_1.value: 60 * 24 * 30,
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