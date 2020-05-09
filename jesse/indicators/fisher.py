import numpy as np
import tulipy as ti

from collections import namedtuple

FisherTransform = namedtuple('FisherTransform', ['fisher', 'signal'])


def fisher(candles: np.ndarray, period=9, sequential=False) -> FisherTransform:
    """
    The Fisher Transform helps identify price reversals.

    :param candles: np.ndarray
    :param period: int - default: 9
    :param sequential: bool - default=False

    :return: FisherTransform
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    fisher, fisher_signal = ti.fisher(np.ascontiguousarray(candles[:, 3]), np.ascontiguousarray(candles[:, 4]),
                                      period=period)

    if sequential:
        return FisherTransform(fisher, fisher_signal)
    else:
        return FisherTransform(fisher[-1], fisher_signal[-1])
