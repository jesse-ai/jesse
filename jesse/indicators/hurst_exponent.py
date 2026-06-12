import numpy as np
import jesse_rust as jr
from scipy import signal as scipy_signal
from jesse.helpers import get_candle_source, slice_candles


def hurst_exponent(candles: np.ndarray, min_chunksize: int = 8, max_chunksize: int = 200, num_chunksize: int = 5, method: int = 1, source_type: str = "close") -> float:
    """Hurst Exponent"""
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, False)
        source = get_candle_source(candles, source_type=source_type)
    if method == 0:
        h = jr.hurst_rs(np.ascontiguousarray(np.diff(source), dtype=np.float64), min_chunksize, max_chunksize, num_chunksize)
    elif method == 1:
        h = _hurst_dma(source, min_chunksize, max_chunksize, num_chunksize)
    elif method == 2:
        h = _hurst_dsod(source)
    else:
        raise NotImplementedError("The method chosen is not implemented.")
    return None if np.isnan(h) else h


def _hurst_dma(prices, min_chunksize=8, max_chunksize=200, num_chunksize=5):
    max_chunksize += 1
    N = len(prices)
    n_list = np.arange(min_chunksize, max_chunksize, num_chunksize, dtype=np.int64)
    dma_list = np.empty(len(n_list))
    factor = 1 / (N - max_chunksize)
    for i, n in enumerate(n_list):
        b = np.divide([n - 1] + (n - 1) * [-1], n)
        noise = np.power(scipy_signal.lfilter(b, 1, prices)[max_chunksize:], 2)
        dma_list[i] = np.sqrt(factor * np.sum(noise))
    H, _ = np.linalg.lstsq(
        a=np.vstack([np.log10(n_list), np.ones(len(n_list))]).T,
        b=np.log10(dma_list), rcond=None
    )[0]
    return H


def _hurst_dsod(x):
    y = np.cumsum(np.diff(x, axis=0), axis=0)
    b1 = [1, -2, 1]
    y1 = scipy_signal.lfilter(b1, 1, y, axis=0)[len(b1)-1:]
    b2 = [1, 0, -2, 0, 1]
    y2 = scipy_signal.lfilter(b2, 1, y, axis=0)[len(b2)-1:]
    s1 = np.mean(y1 ** 2, axis=0)
    s2 = np.mean(y2 ** 2, axis=0)
    return 0.5 * np.log2(s2 / s1)
