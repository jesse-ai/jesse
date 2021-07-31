from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, slice_candles


def ma(candles: np.ndarray, period: int = 30, matype: int = 0,  source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    MA - (nearly) All Moving Averages of Jesse

    :param candles: np.ndarray
    :param period: int - default: 30
    :param matype: int - default: 0
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """

    # Accept normal array too.
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    if matype <= 8:
        from talib import MA
        res = MA(source, timeperiod=period, matype=matype)
    elif matype == 9:
        from . import fwma
        res = fwma(source, period, source_type=source_type, sequential=True)
    elif matype == 10:
        from . import hma
        res = hma(source, period, source_type=source_type,  sequential=True)
    elif matype == 11:
        from talib import LINEARREG
        res = LINEARREG(source, period)
    elif matype == 12:
        from . import wilders
        res = wilders(source, period, source_type=source_type,  sequential=True)
    elif matype == 13:
        from . import sinwma
        res = sinwma(source, period, source_type=source_type,  sequential=True)
    elif matype == 14:
        from . import supersmoother
        res = supersmoother(source, period, source_type=source_type,  sequential=True)
    elif matype == 15:
        from . import supersmoother_3_pole
        res = supersmoother_3_pole(source, period, source_type=source_type,  sequential=True)
    elif matype == 16:
        from . import gauss
        res = gauss(source, period, source_type=source_type,  sequential=True)
    elif matype == 17:
        from . import high_pass
        res = high_pass(source, period, source_type=source_type,  sequential=True)
    elif matype == 18:
        from . import high_pass_2_pole
        res = high_pass_2_pole(source, period, source_type=source_type,  sequential=True)
    elif matype == 19:
        from talib import HT_TRENDLINE
        res = HT_TRENDLINE(source)
    elif matype == 20:
        from . import jma
        res = jma(source, period, source_type=source_type,  sequential=True)
    elif matype == 21:
        from . import reflex
        res = reflex(source, period, source_type=source_type,  sequential=True)
    elif matype == 22:
        from . import trendflex
        res = trendflex(source, period, source_type=source_type,  sequential=True)
    elif matype == 23:
        from . import smma
        res = smma(source, period, source_type=source_type,  sequential=True)
    elif matype == 24:
        if len(candles.shape) == 1:
          raise ValueError("vwma only works with normal candles.")
        from . import vwma
        res = vwma(candles, period, source_type=source_type,  sequential=True)
    elif matype == 25:
        from . import pwma
        res = pwma(source, period, source_type=source_type,  sequential=True)
    elif matype == 26:
        from . import swma
        res = swma(source, period, source_type=source_type,  sequential=True)
    elif matype == 27:
        from . import alma
        res = alma(source, period, source_type=source_type,  sequential=True)
    elif matype == 28:
        from . import hwma
        res = hwma(source, source_type=source_type,  sequential=True)
    elif matype == 29:
        from . import vwap
        if len(candles.shape) == 1:
          raise ValueError("vwap only works with normal candles.")
        res = vwap(source, source_type=source_type,  sequential=True)
    elif matype == 30:
        from . import nma
        res = nma(source, period, source_type=source_type,  sequential=True)
    elif matype == 31:
        from . import edcf
        res = edcf(source, period, source_type=source_type,  sequential=True)
    elif matype == 32:
        from . import mwdx
        res = mwdx(source, source_type=source_type,  sequential=True)
    elif matype == 33:
        from . import maaq
        res = maaq(source, period, source_type=source_type,  sequential=True)
    elif matype == 34:
        from . import srwma
        res = srwma(source, period, source_type=source_type,  sequential=True)
    elif matype == 35:
        from . import sqwma
        res = sqwma(source, period, source_type=source_type,  sequential=True)
    elif matype == 36:
        from . import vpwma
        res = vpwma(source, period, source_type=source_type,  sequential=True)
    elif matype == 37:
        from . import cwma
        res = cwma(source, period, source_type=source_type,  sequential=True)
    elif matype == 38:
        from . import jsa
        res = jsa(source, period, source_type=source_type,  sequential=True)
    elif matype == 39:
        from . import epma
        res = epma(source, period, source_type=source_type,  sequential=True)

    return res if sequential else res[-1]
