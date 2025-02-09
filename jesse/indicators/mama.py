from collections import namedtuple

import numpy as np
from numba import njit

from jesse.helpers import get_candle_source, slice_candles

MAMA = namedtuple('MAMA', ['mama', 'fama'])


def mama(candles: np.ndarray, fastlimit: float = 0.5, slowlimit: float = 0.05, source_type: str = "close",
         sequential: bool = False) -> MAMA:
    """
    MAMA - MESA Adaptive Moving Average (custom implementation)


    :param candles: np.ndarray of candle data or price series
    :param fastlimit: float - default: 0.5
    :param slowlimit: float - default: 0.05
    :param source_type: str - default: "close"
    :param sequential: bool - if True, returns full arrays; else returns only the last value
    :return: MAMA(mama, fama)
    """
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    n = len(source)
    mama_arr = np.zeros(n)
    fama_arr = np.zeros(n)

    # Initialize first element
    mama_arr[0] = source[0]
    fama_arr[0] = source[0]

    mama_arr, fama_arr = fast_mama(source, fastlimit, slowlimit)
    
    # Iterate over the series to compute the indicator recursively
    if sequential:
        return MAMA(mama_arr, fama_arr)
    else:
        return MAMA(mama_arr[-1], fama_arr[-1])

@njit(cache=True)
def fast_mama(source, fastlimit, slowlimit):
    n = len(source)
    sp = np.zeros(n)
    dt = np.zeros(n)
    q1 = np.zeros(n)
    i1_arr = np.zeros(n)
    jI = np.zeros(n)
    jq = np.zeros(n)
    i2_arr = np.zeros(n)
    q2_arr = np.zeros(n)
    re_arr = np.zeros(n)
    im_arr = np.zeros(n)
    p1_arr = np.zeros(n)
    p2_arr = np.zeros(n)
    p3_arr = np.zeros(n)
    p_arr = np.zeros(n)
    spp = np.zeros(n)
    phase = np.zeros(n)
    dphase = np.zeros(n)
    alpha_arr = np.zeros(n)
    mama_arr = np.zeros(n)
    fama_arr = np.zeros(n)
    pi = 3.1415926
    
    for i in range(1, n):
        # sp: weighted average of the source over 4 bars
        sp[i] = (4 * source[i] +
                 3 * (source[i-1] if i-1 >= 0 else 0) +
                 2 * (source[i-2] if i-2 >= 0 else 0) +
                 (source[i-3] if i-3 >= 0 else 0)) / 10.0
        
        dt[i] = (0.0962 * sp[i] +
                 0.5769 * (sp[i-2] if i-2 >= 0 else 0) -
                 0.5769 * (sp[i-4] if i-4 >= 0 else 0) -
                 0.0962 * (sp[i-6] if i-6 >= 0 else 0)) * (0.075 * (p_arr[i-1] if i-1 >= 0 else 0) + 0.54)
        
        q1[i] = (0.0962 * dt[i] +
                 0.5769 * (dt[i-2] if i-2 >= 0 else 0) -
                 0.5769 * (dt[i-4] if i-4 >= 0 else 0) -
                 0.0962 * (dt[i-6] if i-6 >= 0 else 0)) * (0.075 * (p_arr[i-1] if i-1 >= 0 else 0) + 0.54)
        
        i1_arr[i] = dt[i-3] if i-3 >= 0 else 0
        
        jI[i] = (0.0962 * i1_arr[i] +
                 0.5769 * (i1_arr[i-2] if i-2 >= 0 else 0) -
                 0.5769 * (i1_arr[i-4] if i-4 >= 0 else 0) -
                 0.0962 * (i1_arr[i-6] if i-6 >= 0 else 0)) * (0.075 * (p_arr[i-1] if i-1 >= 0 else 0) + 0.54)
        
        jq[i] = (0.0962 * q1[i] +
                 0.5769 * (q1[i-2] if i-2 >= 0 else 0) -
                 0.5769 * (q1[i-4] if i-4 >= 0 else 0) -
                 0.0962 * (q1[i-6] if i-6 >= 0 else 0)) * (0.075 * (p_arr[i-1] if i-1 >= 0 else 0) + 0.54)
        
        i2_temp = i1_arr[i] - jq[i]
        q2_temp = q1[i] + jI[i]
        
        i2_arr[i] = 0.2 * i2_temp + 0.8 * (i2_arr[i-1] if i-1 >= 0 else 0)
        q2_arr[i] = 0.2 * q2_temp + 0.8 * (q2_arr[i-1] if i-1 >= 0 else 0)
        
        re_temp = i2_arr[i] * (i2_arr[i-1] if i-1 >= 0 else 0) + q2_arr[i] * (q2_arr[i-1] if i-1 >= 0 else 0)
        im_temp = i2_arr[i] * (q2_arr[i-1] if i-1 >= 0 else 0) - q2_arr[i] * (i2_arr[i-1] if i-1 >= 0 else 0)
        
        re_arr[i] = 0.2 * re_temp + 0.8 * (re_arr[i-1] if i-1 >= 0 else 0)
        im_arr[i] = 0.2 * im_temp + 0.8 * (im_arr[i-1] if i-1 >= 0 else 0)
        
        if im_arr[i] != 0 and re_arr[i] != 0:
            p1_arr[i] = 2 * pi / np.arctan(im_arr[i] / re_arr[i])
        else:
            p1_arr[i] = p_arr[i-1] if i-1 >= 0 else 0
        
        if p1_arr[i] > 1.5 * (p_arr[i-1] if i-1 >= 0 else 0):
            p2 = 1.5 * (p_arr[i-1] if i-1 >= 0 else 0)
        elif p1_arr[i] < 0.67 * (p_arr[i-1] if i-1 >= 0 else 0):
            p2 = 0.67 * (p_arr[i-1] if i-1 >= 0 else 0)
        else:
            p2 = p1_arr[i]
        p2_arr[i] = p2
        
        p3_arr[i] = 6 if p2_arr[i] < 6 else (50 if p2_arr[i] > 50 else p2_arr[i])
        p_arr[i] = 0.2 * p3_arr[i] + 0.8 * (p_arr[i-1] if i-1 >= 0 else 0)
        spp[i] = 0.33 * p_arr[i] + 0.67 * (spp[i-1] if i-1 >= 0 else 0)
        
        phase[i] = (180 / pi) * np.arctan(q1[i] / i1_arr[i]) if i1_arr[i] != 0 else 0
        dphase_val = (phase[i-1] if i-1 >= 0 else 0) - phase[i]
        dphase_val = dphase_val if dphase_val >= 1 else 1
        dphase[i] = dphase_val
        
        alpha_temp = fastlimit / dphase[i]
        if alpha_temp < slowlimit:
            alpha_arr[i] = slowlimit
        elif alpha_temp > fastlimit:
            alpha_arr[i] = fastlimit
        else:
            alpha_arr[i] = alpha_temp
        
        mama_arr[i] = alpha_arr[i] * source[i] + (1 - alpha_arr[i]) * (mama_arr[i-1] if i-1 >= 0 else source[i])
        fama_arr[i] = 0.5 * alpha_arr[i] * mama_arr[i] + (1 - 0.5 * alpha_arr[i]) * (fama_arr[i-1] if i-1 >= 0 else source[i])
    
    return mama_arr, fama_arr