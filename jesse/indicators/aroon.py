from collections import namedtuple

import numpy as np

from jesse.helpers import slice_candles

AROON = namedtuple('AROON', ['down', 'up'])


def aroon(candles: np.ndarray, period: int = 14, sequential: bool = False) -> AROON:
    """
    AROON indicator

    Calculation:
        For each window of period+1 candles:
            aroon_up   = 100 * (np.argmax(window_high) / period)
            aroon_down = 100 * (np.argmin(window_low)  / period)
        This mimics the PineScript formulas:
            upper = 100 * (ta.highestbars(high, period + 1) + period)/period
            lower = 100 * (ta.lowestbars(low, period + 1) + period)/period
        where ta.highestbars returns a negative offset such that (np.argmax + period) equals the number of periods since the highest high.

    :param candles: np.ndarray, expected to have at least 5 columns, with high at index 3 and low at index 4.
    :param period: int - period for the indicator (default: 14)
    :param sequential: bool - whether to return the whole series (default: False)
    :return: AROON(down, up) where each value is computed as above.
    """
    candles = slice_candles(candles, sequential)
    highs = candles[:, 3]
    lows = candles[:, 4]

    if sequential:
        # Initialize result arrays with NaN
        aroon_up = np.full(highs.shape, np.nan, dtype=float)
        aroon_down = np.full(lows.shape, np.nan, dtype=float)
        
        # Compute indicator for each valid index (starting from period index)
        for i in range(period, len(highs)):
            window_high = highs[i - period:i + 1]  # period+1 values
            window_low = lows[i - period:i + 1]
            # np.argmax returns the index of the first occurrence of the max value in the window.
            # When maximum is at the current bar, np.argmax(window_high) == period, yielding 100 * (period/period) = 100.
            aroon_up[i] = 100 * (np.argmax(window_high) / period)
            aroon_down[i] = 100 * (np.argmin(window_low) / period)
        return AROON(down=aroon_down, up=aroon_up)
    else:
        if len(highs) < period + 1:
            up_val = float('nan')
            down_val = float('nan')
        else:
            window_high = highs[-(period + 1):]
            window_low = lows[-(period + 1):]
            up_val = 100 * (np.argmax(window_high) / period)
            down_val = 100 * (np.argmin(window_low) / period)
        return AROON(down=down_val, up=up_val)
