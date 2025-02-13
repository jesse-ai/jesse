from collections import namedtuple
import numpy as np
from numba import njit
from jesse.helpers import get_candle_source, np_shift, slice_candles

AG = namedtuple('AG', ['jaw', 'teeth', 'lips'])

def smma(source: np.ndarray, length: int) -> np.ndarray:
    return _smma_numba(source, length)

@njit
def _smma_numba(source, length):
    alpha = 1.0 / length
    total = 0.0
    for i in range(length):
        total += source[i]
    init_val = total / length
    N = len(source)
    result = np.empty(N, dtype=np.float64)
    result[0] = alpha * source[0] + (init_val * (1 - alpha))
    for i in range(1, N):
        result[i] = alpha * source[i] + (1 - alpha) * result[i-1]
    return result

def alligator(candles: np.ndarray, source_type: str = "hl2", sequential: bool = False) -> AG:
    candles = slice_candles(candles, sequential)
    source = get_candle_source(candles, source_type=source_type)

    jaw = np_shift(smma(source, 13), 8, fill_value=np.nan)
    teeth = np_shift(smma(source, 8), 5, fill_value=np.nan)
    lips = np_shift(smma(source, 5), 3, fill_value=np.nan)

    if sequential:
        return AG(jaw, teeth, lips)
    else:
        return AG(jaw[-1], teeth[-1], lips[-1])
