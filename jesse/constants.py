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