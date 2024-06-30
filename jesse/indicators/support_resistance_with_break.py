from collections import namedtuple

import numpy as np
from .ema import ema

SupportResistanceWithBreaks = namedtuple('SupportResistanceWithBreaks', ['support', 'resistance', 'red_break', 'green_break', 'bear_wick', 'bull_wick'])


def support_resistance_with_breaks(candles: np.ndarray, left_bars: int = 15, right_bars: int = 15, vol_threshold: int = 20) -> SupportResistanceWithBreaks:
    """
    support_resistance_with_breaks

    @author LuxAlgo
    credits: https://www.tradingview.com/script/JDFoWQbL-Support-and-Resistance-Levels-with-Breaks-LuxAlgo

    :param candles: np.ndarray
    :param left_bars: int - default: 15
    :param right_bars: int - default: 15
    :param vol_threshold: int - default: 20
    :return: SupportResistanceWithBreaks(support, resistance, red_break, green_break, bear_wick, bull_wick)
    """
    resistance = _resistance(candles[:, 3], left_bars, right_bars)
    support = _support(candles[:, 4], left_bars, right_bars)

    short = ema(candles[:, 5], 5)
    long = ema(candles[:, 5], 10)
    osc = 100 * (short - long) / long

    last_candles = candles[0]

    red_break = True if last_candles[2] < support and not abs(
        last_candles[1] - last_candles[2]) < abs(last_candles[1] - last_candles[3]) and osc > vol_threshold else False
    green_break = True if last_candles[2] > resistance and abs(
        last_candles[1] - last_candles[4]) > abs(last_candles[1] - last_candles[2]) and osc > vol_threshold else False

    bull_wick = True if last_candles[2] > resistance and abs(last_candles[1] - last_candles[4]) > abs(last_candles[1] - last_candles[2]) else False
    bear_wick = True if last_candles[2] < support and abs(last_candles[1] - last_candles[2]) < abs(last_candles[1] - last_candles[3]) else False

    return SupportResistanceWithBreaks(support, resistance, red_break, green_break, bear_wick, bull_wick)


def _resistance(source, left_bars, right_bars):
    pivot_highs = [None] * len(source)  # Initialize result list with None

    for i in range(left_bars, len(source) - right_bars):
        is_pivot_high = True

        # Check left bars for higher high
        for j in range(1, left_bars + 1):
            if source[i] <= source[i - j]:
                is_pivot_high = False
                break

        # Check right bars for higher high
        if is_pivot_high:
            for j in range(1, right_bars + 1):
                if source[i] <= source[i + j]:
                    is_pivot_high = False
                    break

        if is_pivot_high:
            is_pivot_high = source[i]

        pivot_highs[i] = is_pivot_high

    next_valid = None
    first_value = None
    for i in range(len(pivot_highs)):
        if pivot_highs[i] is False:
            pivot_highs[i] = next_valid
        elif pivot_highs[i] is not None:  # Update next_valid if it's not False or None
            next_valid = pivot_highs[i]
            first_value = i if first_value is None else first_value

    pivot_highs[:first_value - 1] = [pivot_highs[first_value]] * len(pivot_highs[:first_value - 1])
    pivot_highs[-right_bars:] = [pivot_highs[-right_bars - 1]] * len(pivot_highs[-right_bars:])

    return pivot_highs[-1]


def _support(source, left_bars, right_bars):
    pivot_lows = [None] * len(source)  # Initialize result list with None

    for i in range(left_bars, len(source) - right_bars):
        is_pivot_low = True

        # Check left bars for lower low
        for j in range(1, left_bars + 1):
            if source[i] >= source[i - j]:
                is_pivot_low = False
                break

        # Check right bars for lower low
        if is_pivot_low:
            for j in range(1, right_bars + 1):
                if source[i] >= source[i + j]:
                    is_pivot_low = False
                    break

        if is_pivot_low:
            is_pivot_low = source[i]

        pivot_lows[i] = is_pivot_low

    next_valid = None
    first_value = None
    for i in range(len(pivot_lows)):
        if pivot_lows[i] is False:
            pivot_lows[i] = next_valid
        elif pivot_lows[i] is not None:  # Update next_valid if it's not False or None
            next_valid = pivot_lows[i]
            first_value = i if first_value is None else first_value

    pivot_lows[:first_value - 1] = [pivot_lows[first_value]] * len(pivot_lows[:first_value - 1])
    pivot_lows[-right_bars:] = [pivot_lows[-right_bars - 1]] * len(pivot_lows[-right_bars:])

    return pivot_lows[-1]
