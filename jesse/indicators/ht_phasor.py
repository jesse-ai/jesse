from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import get_candle_source
from jesse.helpers import slice_candles

IQ = namedtuple('IQ', ['inphase', 'quadrature'])


def ht_phasor(candles: np.ndarray, source_type: str = "close", sequential: bool = False) -> IQ:
    """
    HT_PHASOR - Hilbert Transform - Phasor Components

    :param candles: np.ndarray
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: IQ(inphase, quadrature)
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    inphase, quadrature = talib.HT_PHASOR(source)

    if sequential:
        return IQ(inphase, quadrature)
    else:
        return IQ(inphase[-1], quadrature[-1])
