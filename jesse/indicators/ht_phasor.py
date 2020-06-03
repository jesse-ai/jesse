from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import get_candle_source

IQ = namedtuple('IQ', ['inphase', 'quadrature'])

def ht_phasor(candles: np.ndarray, source_type="close", sequential=False) -> IQ:
    """
    HT_PHASOR - Hilbert Transform - Phasor Components

    :param candles: np.ndarray
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: IQ(inphase, quadrature)
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)
    inphase, quadrature = talib.HT_PHASOR(source)

    if sequential:
        return IQ(inphase, quadrature)
    else:
        return IQ(inphase[-1], quadrature[-1])
