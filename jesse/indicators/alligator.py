from collections import namedtuple
import numpy as np
from jesse.helpers import get_candle_source, slice_candles
from jesse_rust import smma, shift, alligator as alligator_rust

AG = namedtuple('AG', ['jaw', 'teeth', 'lips'])

def alligator(candles: np.ndarray, source_type: str = "hl2", sequential: bool = False) -> AG:
    """
    Alligator indicator by Bill Williams
    
    :param candles: np.ndarray
    :param source_type: str - default: "hl2"
    :param sequential: bool - default: False

    :return: AG(jaw, teeth, lips)
    """
    candles = slice_candles(candles, sequential)
    source = get_candle_source(candles, source_type=source_type)
    
    # Use Rust implementation for calculating the alligator
    jaw, teeth, lips = alligator_rust(source)
    
    if sequential:
        return AG(jaw, teeth, lips)
    else:
        return AG(jaw[-1], teeth[-1], lips[-1])
