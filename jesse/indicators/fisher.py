from collections import namedtuple

import numpy as np
import tulipy as ti

from jesse.helpers import get_config

FisherTransform = namedtuple('FisherTransform', ['fisher', 'signal'])


def fisher(candles: np.ndarray, period: int = 9, sequential: bool = False) -> FisherTransform:
    """
    The Fisher Transform helps identify price reversals.

    :param candles: np.ndarray
    :param period: int - default: 9
    :param sequential: bool - default=False

    :return: FisherTransform(fisher, signal)
    """
    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    fisher, fisher_signal = ti.fisher(np.ascontiguousarray(candles[:, 3]), np.ascontiguousarray(candles[:, 4]),
                                      period=period)

    if sequential:
        return FisherTransform(np.concatenate((np.full((candles.shape[0] - fisher.shape[0]), np.nan), fisher), axis=0),
                               np.concatenate(
                                   (np.full((candles.shape[0] - fisher_signal.shape[0]), np.nan), fisher_signal)))
    else:
        return FisherTransform(fisher[-1], fisher_signal[-1])
