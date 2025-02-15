import numpy as np

from typing import Union

from jesse.helpers import get_candle_source, slice_candles


def rocr(candles: np.ndarray, period: int = 10, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    ROCR - Rate of change ratio: (price / price_lagged)

    :param candles: np.ndarray
    :param period: int - default: 10
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)
    source = get_candle_source(candles, source_type=source_type)

    # Initialize an array of NaNs with the same shape as source
    res = np.full(source.shape, np.nan, dtype=float)
    
    # Only compute if there are enough data points
    if source.shape[0] > period:
        # Compute rate of change ratio using vectorized operation; for indices < period, remains NaN
        res[period:] = source[period:] / source[:-period]

    return res if sequential else res[-1]
