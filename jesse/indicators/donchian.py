from collections import namedtuple

import numpy as np
from jesse_rust import donchian as rust_donchian
from jesse.helpers import slice_candles

DonchianChannel = namedtuple('DonchianChannel', ['upperband', 'middleband', 'lowerband'])


def donchian(candles: np.ndarray, period: int = 20, sequential: bool = False) -> DonchianChannel:
    """
    Donchian Channels

    :param candles: np.ndarray
    :param period: int - default: 20
    :param sequential: bool - default: False

    :return: DonchianChannel(upperband, middleband, lowerband)
    """
    candles = slice_candles(candles, sequential)
    
    if sequential:
        # Use optimized Rust implementation
        rust_result = rust_donchian(candles, period)
        return DonchianChannel(
            rust_result['upperband'],
            rust_result['middleband'],
            rust_result['lowerband']
        )
    else:
        # Non-sequential mode only needs the very last value of the channel.
        # Instead of calling the Rust implementation (which processes the
        # entire candle history and incurs extra FFI overhead), we can obtain
        # the same result in pure NumPy by looking at just the last `period`
        # candles.

        if candles.shape[0] < period:
            # Not enough candles yet → behave exactly like the Rust variant
            # which would return NaNs for the incomplete window.
            return DonchianChannel(np.nan, np.nan, np.nan)

        # Slice only the window we need.
        window = candles[-period:]

        # Candle columns: 0 -> timestamp, 1 -> open, 2 -> close, 3 -> high, 4 -> low
        highs = window[:, 3]
        lows = window[:, 4]

        upper = highs.max()
        lower = lows.min()
        middle = (upper + lower) / 2

        return DonchianChannel(upper, middle, lower)
