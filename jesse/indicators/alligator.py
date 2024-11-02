from collections import namedtuple
import numpy as np
from scipy.signal import lfilter
from jesse.helpers import get_candle_source, np_shift, slice_candles

AG = namedtuple('AG', ['jaw', 'teeth', 'lips'])

def smma(source: np.ndarray, length: int) -> np.ndarray:
    alpha = 1 / length
    initial_value = np.mean(source[:length])
    smma, _ = lfilter([alpha], [1, -(1 - alpha)], source, zi=[initial_value * (1 - alpha)])
    return smma

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
