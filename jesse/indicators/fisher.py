from collections import namedtuple

import numpy as np
import tulipy as ti

FisherTransform = namedtuple('FisherTransform', ['fisher', 'signal'])


def fisher(candles: np.ndarray, period=9, sequential=False) -> FisherTransform:
    """
    The Fisher Transform helps identify price reversals.

    :param candles: np.ndarray
    :param period: int - default: 9
    :param sequential: bool - default=False

    :return: FisherTransform(fisher, signal)
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    fisher, fisher_signal = ti.fisher(np.ascontiguousarray(candles[:, 3]), np.ascontiguousarray(candles[:, 4]),
                                      period=period)

    if sequential:
        return FisherTransform(np.concatenate((np.full((candles.shape[0] - fisher.shape[0]), np.nan), fisher), axis=0),
                               np.concatenate(
                                   (np.full((candles.shape[0] - fisher_signal.shape[0]), np.nan), fisher_signal)))
    else:
        return FisherTransform(fisher[-1], fisher_signal[-1])
