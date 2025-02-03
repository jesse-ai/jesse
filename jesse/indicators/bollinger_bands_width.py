from typing import Union
import numpy as np
from jesse.helpers import get_candle_source, slice_candles


def bollinger_bands_width(candles: np.ndarray, period: int = 20, mult: float = 2.0, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    BBW - Bollinger Bands Width - Bollinger Bands Bandwidth

    :param candles: np.ndarray
    :param period: int - default: 20
    :param mult: float - default: 2
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: BollingerBands(upperband, middleband, lowerband)
    """
    candles = slice_candles(candles, sequential)
    source = get_candle_source(candles, source_type=source_type)

    if sequential:
        n = len(source)
        bbw = np.full(n, np.nan)
        if n >= period:
            windows = np.lib.stride_tricks.sliding_window_view(source, window_shape=period)
            basis = np.mean(windows, axis=1)
            std = np.std(windows, axis=1, ddof=0)
            # Compute Bollinger Bands Width using vectorized operation
            bbw[period - 1:] = (( (basis + mult * std) - (basis - mult * std) ) / basis)
        return bbw
    else:
        window = source[-period:]
        basis = np.mean(window)
        std = np.std(window, ddof=0)
        upper = basis + mult * std
        lower = basis - mult * std
        return ((upper - lower) / basis)
