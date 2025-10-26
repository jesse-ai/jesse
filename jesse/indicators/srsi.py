from collections import namedtuple

import numpy as np

from jesse.helpers import get_candle_source, slice_candles

# Import the high-performance Rust implementation
from jesse_rust import srsi as srsi_rust  # type: ignore

StochasticRSI = namedtuple('StochasticRSI', ['k', 'd'])


def srsi(
    candles: np.ndarray,
    period: int = 14,
    period_stoch: int = 14,
    k: int = 3,
    d: int = 3,
    source_type: str = "close",
    sequential: bool = False,
) -> StochasticRSI:
    """Stochastic RSI – uses Rust implementation for speed."""
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    k_line, d_line = srsi_rust(source.astype(np.float64), period, period_stoch, k, d)

    if sequential:
        return StochasticRSI(k_line, d_line)
    else:
        return StochasticRSI(float(k_line[-1]), float(d_line[-1]))
