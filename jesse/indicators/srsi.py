from collections import namedtuple

import numpy as np

from jesse.helpers import get_candle_source, slice_candles
from jesse.indicators.rsi import rsi as rsi_py
from jesse.indicators.sma import sma as sma_py

# Try to import the high-performance Rust implementation
try:
    from jesse_rust import srsi as srsi_rust  # type: ignore
except ImportError:  # pragma: no cover – rust module missing only in dev envs
    srsi_rust = None  # type: ignore

StochasticRSI = namedtuple('StochasticRSI', ['k', 'd'])


def _srsi_numpy(source: np.ndarray, period: int, period_stoch: int, k: int, d: int) -> tuple[np.ndarray, np.ndarray]:
    """Pure-NumPy fallback – kept for environments without the Rust extension."""
    rsi_values = rsi_py(source, period=period, sequential=True)
    rsi_values = np.asarray(rsi_values, dtype=np.float64)
    n = len(rsi_values)

    stoch_rsi = np.full(n, np.nan)
    for i in range(period_stoch - 1, n):
        window = rsi_values[i + 1 - period_stoch : i + 1]
        min_rsi = np.nanmin(window)
        max_rsi = np.nanmax(window)
        if max_rsi > min_rsi:
            stoch_rsi[i] = 100 * (rsi_values[i] - min_rsi) / (max_rsi - min_rsi)

    k_line = sma_py(stoch_rsi, k, sequential=True)
    d_line = sma_py(k_line, d, sequential=True)
    return k_line, d_line


def srsi(
    candles: np.ndarray,
    period: int = 14,
    period_stoch: int = 14,
    k: int = 3,
    d: int = 3,
    source_type: str = "close",
    sequential: bool = False,
) -> StochasticRSI:
    """Stochastic RSI – uses Rust implementation when available for speed."""
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    # Prefer Rust version if present
    if srsi_rust is not None:
        k_line, d_line = srsi_rust(source.astype(np.float64), period, period_stoch, k, d)
    else:
        k_line, d_line = _srsi_numpy(source, period, period_stoch, k, d)

    if sequential:
        return StochasticRSI(k_line, d_line)
    else:
        return StochasticRSI(float(k_line[-1]), float(d_line[-1]))
