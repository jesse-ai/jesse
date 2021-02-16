from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import get_candle_source
from jesse.helpers import get_config

IQ = namedtuple('IQ', ['inphase', 'quadrature'])


def ht_phasor(candles: np.ndarray, source_type: str = "close", sequential: bool = False) -> IQ:
    """
    HT_PHASOR - Hilbert Transform - Phasor Components

    :param candles: np.ndarray
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: IQ(inphase, quadrature)
    """
    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    source = get_candle_source(candles, source_type=source_type)
    inphase, quadrature = talib.HT_PHASOR(source)

    if sequential:
        return IQ(inphase, quadrature)
    else:
        return IQ(inphase[-1], quadrature[-1])
