from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, same_length, slice_candles


def vwma(candles: np.ndarray, period: int = 20, source_type: str = "close", sequential: bool = False) -> Union[
        float, np.ndarray]:
    """
    VWMA - Volume Weighted Moving Average

    :param candles: np.ndarray
    :param period: int - default: 20
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    if len(candles.shape) == 1:
        source = candles
        volume = np.ones_like(candles)
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)
        volume = candles[:, 5]

    # Calculate price * volume
    weighted = source * volume
    
    # Compute cumulative sums for weighted price and volume
    cumsum_weighted = np.cumsum(weighted)
    cumsum_volume = np.cumsum(volume)

    # Allocate array for VWMA values
    vwma_vals = np.empty_like(source, dtype=float)

    # For initial indices where full period is not available, use cumulative sums
    vwma_vals[:period] = cumsum_weighted[:period] / np.where(cumsum_volume[:period] == 0, 1, cumsum_volume[:period])

    # For indices with a complete period, use the rolling difference of cumulative sums
    vwma_vals[period:] = (cumsum_weighted[period:] - cumsum_weighted[:-period]) / np.where((cumsum_volume[period:] - cumsum_volume[:-period]) == 0, 1, (cumsum_volume[period:] - cumsum_volume[:-period]))

    return same_length(candles, vwma_vals) if sequential else vwma_vals[-1]
