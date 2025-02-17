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

    0: sma (simple)
    1: ema (exponential)
    2: wma (weighted)
    3: dema (double exponential)
    4: tema (triple exponential)
    5: trima (triangular)
    6: kama (Kaufman adaptive)
    9: fwma (Fibonacci's Weighted Moving Average)
    10: hma (Hull Moving Average)
    11: linearreg (Linear Regression)
    12: wilders (Wilders Smoothing)
    13: sinwma (Sine Weighted Moving Average)
    14: supersmoother (Super Smoother Filter 2pole Butterworth)
    15: supersmoother\_3\_pole(Super Smoother Filter 3pole Butterworth)
    16: gauss (Gaussian Filter)
    17: high\_pass (1-pole High Pass Filter by John F. Ehlers)
    18: high\_pass\_2\_pole (2-pole High Pass Filter by John F. Ehlers)
    19: ht\_trendline (Hilbert Transform - Instantaneous Trendline)
    20: jma (Jurik Moving Average)
    21: reflex (Reflex indicator by John F. Ehlers)
    22: trendflex (Trendflex indicator by John F. Ehlers)
    23: smma (Smoothed Moving Average)
    24: vwma (Volume Weighted Moving Average)
    25: pwma (Pascals Weighted Moving Average)
    26: swma (Symmetric Weighted Moving Average)
    27: alma (Arnaud Legoux Moving Average)
    28: hwma (Holt-Winter Moving Average)
    29: vwap (Volume weighted average price)
    30: nma (Natural Moving Average)
    31: edcf (Ehlers Distance Coefficient Filter)
    32: mwdx (MWDX Average)
    33: maaq (Moving Average Adaptive Q)
    34: srwma (Square Root Weighted Moving Average)
    35: sqwma (Square Weighted Moving Average)
    36: vpwma (Variable Power Weighted Moving Average)
    37: cwma (Cubed Weighted Moving Average)
    38: jsa (Jsa Moving Average)
    39: epma (End Point Moving Average)

    """

    candles = slice_candles(candles, sequential)

    if matype == 0:
        from . import sma
        res = sma(candles, period, source_type=source_type, sequential=True)
    elif matype == 1:
        from . import ema
        res = ema(candles, period, source_type=source_type, sequential=True)
    elif matype == 2:
        from . import wma
        res = wma(candles, period, source_type=source_type, sequential=True)
    elif matype == 3:
        from . import dema
        res = dema(candles, period, source_type=source_type, sequential=True)
    elif matype == 4:
        from . import tema
        res = tema(candles, period, source_type=source_type, sequential=True)
    elif matype == 5:
        from . import trima
        res = trima(candles, period, source_type=source_type, sequential=True)
    elif matype == 6:
        from . import kama
        res = kama(candles, period, source_type=source_type, sequential=True)
    elif matype == 9:
        from . import fwma
        res = fwma(candles, period, source_type=source_type, sequential=True)
    elif matype == 10:
        from . import hma
        res = hma(candles, period, source_type=source_type,  sequential=True)
    elif matype == 11:
        from . import linearreg
        res = linearreg(candles, period, source_type=source_type, sequential=True)
    elif matype == 12:
        from . import wilders
        res = wilders(candles, period, source_type=source_type,  sequential=True)
    elif matype == 13:
        from . import sinwma
        res = sinwma(candles, period, source_type=source_type,  sequential=True)
    elif matype == 14:
        from . import supersmoother
        res = supersmoother(candles, period, source_type=source_type,  sequential=True)
    elif matype == 15:
        from . import supersmoother_3_pole
        res = supersmoother_3_pole(candles, period, source_type=source_type,  sequential=True)
    elif matype == 16:
        from . import gauss
        res = gauss(candles, period, source_type=source_type,  sequential=True)
    elif matype == 17:
        from . import high_pass
        res = high_pass(candles, period, source_type=source_type,  sequential=True)
    elif matype == 18:
        from . import high_pass_2_pole
        res = high_pass_2_pole(candles, period, source_type=source_type,  sequential=True)
    elif matype == 20:
        from . import jma
        res = jma(candles, period, source_type=source_type,  sequential=True)
    elif matype == 21:
        from . import reflex
        res = reflex(candles, period, source_type=source_type,  sequential=True)
    elif matype == 22:
        from . import trendflex
        res = trendflex(candles, period, source_type=source_type,  sequential=True)
    elif matype == 23:
        from . import smma
        res = smma(candles, period, source_type=source_type,  sequential=True)
    elif matype == 24:
        if len(candles.shape) == 1:
          raise ValueError("vwma only works with normal candles.")
        from . import vwma
        res = vwma(candles, period, source_type=source_type,  sequential=True)
    elif matype == 25:
        from . import pwma
        res = pwma(candles, period, source_type=source_type,  sequential=True)
    elif matype == 26:
        from . import swma
        res = swma(candles, period, source_type=source_type,  sequential=True)
    elif matype == 27:
        from . import alma
        res = alma(candles, period, source_type=source_type,  sequential=True)
    elif matype == 28:
        from . import hwma
        res = hwma(candles, source_type=source_type,  sequential=True)
    elif matype == 29:
        from . import vwap
        if len(candles.shape) == 1:
          raise ValueError("vwap only works with normal candles.")
        res = vwap(candles, source_type=source_type,  sequential=True)
    elif matype == 30:
        from . import nma
        res = nma(candles, period, source_type=source_type,  sequential=True)
    elif matype == 31:
        from . import edcf
        res = edcf(candles, period, source_type=source_type,  sequential=True)
    elif matype == 32:
        from . import mwdx
        res = mwdx(candles, source_type=source_type,  sequential=True)
    elif matype == 33:
        from . import maaq
        res = maaq(candles, period, source_type=source_type,  sequential=True)
    elif matype == 34:
        from . import srwma
        res = srwma(candles, period, source_type=source_type,  sequential=True)
    elif matype == 35:
        from . import sqwma
        res = sqwma(candles, period, source_type=source_type,  sequential=True)
    elif matype == 36:
        from . import vpwma
        res = vpwma(candles, period, source_type=source_type,  sequential=True)
    elif matype == 37:
        from . import cwma
        res = cwma(candles, period, source_type=source_type,  sequential=True)
    elif matype == 38:
        from . import jsa
        res = jsa(candles, period, source_type=source_type,  sequential=True)
    elif matype == 39:
        from . import epma
        res = epma(candles, period, source_type=source_type,  sequential=True)
    elif matype == 7 or matype == 8 or matype == 19:
        raise ValueError("Invalid matype value.")

    return res if sequential else res[-1]
