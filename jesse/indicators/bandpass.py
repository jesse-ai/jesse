from collections import namedtuple

import numpy as np
from numba import njit

from jesse.helpers import get_candle_source, slice_candles

from .high_pass import high_pass_fast

BandPass = namedtuple('BandPass', ['bp', 'bp_normalized', 'signal', 'trigger'])


def bandpass(candles: np.ndarray, period: int = 20, bandwidth: float = 0.3,  source_type: str = "close",  sequential: bool = False) -> BandPass:
    """
    BandPass Filter

    :param candles: np.ndarray
    :param period: int - default: 20
    :param bandwidth: float - default: 0.3
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: BandPass(bp, bp_normalized, signal, trigger)
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)

    hp = high_pass_fast(source, 4 * period / bandwidth)

    beta = np.cos(2 * np.pi / period)
    gamma = np.cos(2 * np.pi * bandwidth / period)
    alpha = 1 / gamma - np.sqrt(1 / gamma ** 2 - 1)

    bp, peak = bp_fast(source, hp, alpha, beta)

    bp_normalized = bp / peak

    trigger = high_pass_fast(bp_normalized, period / bandwidth / 1.5)
    signal = (bp_normalized < trigger) * 1 - (trigger < bp_normalized) * 1

    if sequential:
        return BandPass(bp, bp_normalized, signal, trigger)
    else:
        return BandPass(bp[-1], bp_normalized[-1], signal[-1], trigger[-1])


@njit(cache=True)
def bp_fast(source, hp, alpha, beta):  # Function is compiled to machine code when called the first time

    bp = np.copy(hp)
    for i in range(2, source.shape[0]):
      bp[i] = 0.5 * (1 - alpha) * hp[i] - (1 - alpha) * 0.5 * hp[i - 2]  + beta * (1 + alpha) * bp[i - 1] - alpha * bp[i - 2]

    # fast attack-slow decay AGC
    K = 0.991
    peak = np.copy(bp)
    for i in range(source.shape[0]):
      if i > 0:
        peak[i] = peak[i - 1] * K
      if np.abs(bp[i]) > peak[i]:
        peak[i] = np.abs(bp[i])

    return bp, peak
