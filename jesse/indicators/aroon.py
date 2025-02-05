from collections import namedtuple

import numpy as np

from jesse.helpers import slice_candles

AROON = namedtuple('AROON', ['down', 'up'])


def aroon(candles: np.ndarray, period: int = 14, sequential: bool = False) -> AROON:
    """
    AROON indicator

    :param candles: np.ndarray, expected to have at least 5 columns, with high at index 3 and low at index 4.
    :param period: int - period for the indicator (default: 14)
    :param sequential: bool - whether to return the whole series (default: False)
    :return: AROON(down, up) where each value is computed as above.
    """
    candles = slice_candles(candles, sequential)
    highs = candles[:, 3]
    lows = candles[:, 4]

    if sequential:
        aroon_up = np.full(highs.shape, np.nan, dtype=float)
        aroon_down = np.full(lows.shape, np.nan, dtype=float)
        if len(highs) >= period + 1:
            # Create sliding window view of period+1 elements for highs and lows
            windows_high = np.lib.stride_tricks.sliding_window_view(highs, window_shape=period+1)
            windows_low = np.lib.stride_tricks.sliding_window_view(lows, window_shape=period+1)
            aroon_up[period:] = 100 * (np.argmax(windows_high, axis=1) / period)
            aroon_down[period:] = 100 * (np.argmin(windows_low, axis=1) / period)
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
