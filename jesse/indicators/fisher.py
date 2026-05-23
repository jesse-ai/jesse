from collections import namedtuple
import numpy as np
import jesse_rust as jr
from jesse.helpers import same_length, slice_candles

FisherTransform = namedtuple("FisherTransform", ["fisher", "signal"])

def fisher(candles: np.ndarray, period: int = 9, sequential: bool = False) -> FisherTransform:
    """The Fisher Transform helps identify price reversals."""
    candles = slice_candles(candles, sequential)
    fisher_v, fisher_sig = jr.fisher(np.ascontiguousarray(candles, dtype=np.float64), period)
    if sequential:
        return FisherTransform(same_length(candles, fisher_v), same_length(candles, fisher_sig))
    return FisherTransform(fisher_v[-1], fisher_sig[-1])
