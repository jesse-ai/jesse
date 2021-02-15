from collections import namedtuple

import numpy as np
from numba import njit

from jesse.helpers import get_config

VI = namedtuple('VI', ['plus', 'minus'])


def vi(candles: np.ndarray, period: int = 14, sequential: bool = False) -> VI:
    """
    Vortex Indicator (VI)

    :param candles: np.ndarray
    :param period: int - default=14
    :param sequential: bool - default=False

    :return: VI(plus, minus)
    """
    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    vpn_with_nan, vmn_with_nan = vi_fast(candles, period)

    if sequential:
        return VI(vpn_with_nan, vmn_with_nan)
    else:
        return VI(vpn_with_nan[-1], vmn_with_nan[-1])


@njit
def vi_fast(candles, period):
    candles_close = candles[:, 2]
    candles_high = candles[:, 3]
    candles_low = candles[:, 4]

    tr = np.zeros(len(candles_high))
    vp = np.zeros(len(candles_high))
    vm = np.zeros(len(candles_high))
    trd = np.zeros(len(candles_high))
    vpd = np.zeros(len(candles_high))
    vmd = np.zeros(len(candles_high))
    tr[0] = candles_high[0] - candles_low[0]
    for i in range(1, len(candles_high)):
        hl = candles_high[i] - candles_low[i]
        hpc = np.fabs(candles_high[i] - candles_close[i - 1])
        lpc = np.fabs(candles_low[i] - candles_close[i - 1])
        tr[i] = np.amax(np.array([hl, hpc, lpc]))
        vp[i] = np.fabs(candles_high[i] - candles_low[i - 1])
        vm[i] = np.fabs(candles_low[i] - candles_high[i - 1])
    for j in range(len(candles_high) - period + 1):
        trd[period - 1 + j] = np.sum(tr[j:j + period])
        vpd[period - 1 + j] = np.sum(vp[j:j + period])
        vmd[period - 1 + j] = np.sum(vm[j:j + period])
    trd = trd[period - 1:]
    vpd = vpd[period - 1:]
    vmd = vmd[period - 1:]
    vpn = vpd / trd
    vmn = vmd / trd
    vpn_with_nan = np.concatenate((np.full((candles.shape[0] - vpn.shape[0]), np.nan), vpn))
    vmn_with_nan = np.concatenate((np.full((candles.shape[0] - vmn.shape[0]), np.nan), vmn))
    return vpn_with_nan, vmn_with_nan
