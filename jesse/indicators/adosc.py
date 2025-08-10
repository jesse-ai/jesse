from typing import Union

import numpy as np
from jesse.helpers import slice_candles
from jesse_rust import adosc as adosc_rust


def adosc(candles: np.ndarray, fast_period: int = 3, slow_period: int = 10, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    ADOSC - Chaikin A/D Oscillator (Rust accelerated version)

    :param candles: np.ndarray of candles
    :param fast_period: int - default: 3
    :param slow_period: int - default: 10
    :param sequential: bool - default: False
    :return: float or np.ndarray
    """
    candles = slice_candles(candles, sequential)
    
    # Convert to float64 for Rust compatibility
    candles_f64 = np.asarray(candles, dtype=np.float64)
    
    # Call the Rust implementation
    result = adosc_rust(candles_f64, fast_period, slow_period)

    return result if sequential else result[-1]
