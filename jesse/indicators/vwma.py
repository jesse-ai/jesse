from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, slice_candles
from jesse_rust import vwma as vwma_rust


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
        # Handle 1D array case by creating dummy candles with volume=1
        source = candles
        dummy_candles = np.column_stack([
            np.zeros(len(source)),  # timestamp
            np.zeros(len(source)),  # open
            source,                 # close
            np.zeros(len(source)),  # high
            np.zeros(len(source)),  # low
            np.ones(len(source))    # volume
        ])
        candles_f64 = np.asarray(dummy_candles, dtype=np.float64)
    else:
        candles = slice_candles(candles, sequential)
        # Convert to float64 for Rust compatibility
        candles_f64 = np.asarray(candles, dtype=np.float64)
        
        # Update close column if different source type is requested
        if source_type != "close":
            source = get_candle_source(candles, source_type=source_type)
            candles_f64[:, 2] = source

    # Call the Rust implementation
    result = vwma_rust(candles_f64, period)
    
    return result if sequential else result[-1]
