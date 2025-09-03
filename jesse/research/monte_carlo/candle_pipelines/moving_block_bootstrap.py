import numpy as np
from .base_candles import BaseCandlesPipeline

class MovingBlockBootstrapCandlesPipeline(BaseCandlesPipeline):
    def __init__(self, batch_size: int, **_ignored) -> None:
        """
        Generate synthetic candles by moving-block bootstrap on multivariate
        tuples of (delta_close, delta_high, delta_low).

        Parameters
        ----------
        batch_size : int
            Size of the internal regeneration buffer in minutes. The pipeline
            derives a reasonable bootstrap block length from this, so there is
            no separate block-size argument.
        """
        super().__init__(batch_size)

        # Derive block size from batch size. Heuristic: max(10, batch_size // 10),
        # then clamp to [1, batch_size - 1]. This preserves short-horizon
        # dependence while allowing variety.
        derived_block_size = max(10, batch_size // 10)
        derived_block_size = max(1, min(batch_size - 1, derived_block_size))
        self._block_size = derived_block_size

        # Independent RNG per pipeline instance to avoid identical scenarios
        self._rng = np.random.default_rng()

    def _bootstrap_blocks(self, arr: np.ndarray, n: int) -> np.ndarray:
        """
        Sample overlapping blocks of rows from `arr` to build a length-n output.
        `arr` is shape (T, 3) for the three deltas.
        """
        T, D = arr.shape
        if T == 0:
            return np.zeros((n, 3), dtype=arr.dtype)
        # Use the configured block_size, but not beyond available data
        effective_block_size = max(1, min(self._block_size, T))
        max_start = T - effective_block_size
        # how many blocks needed to reach n rows
        num_blocks = int(np.ceil(n / effective_block_size)) + 1
        starts = self._rng.integers(0, max_start + 1, size=num_blocks)
        blocks = [arr[s : s + effective_block_size] for s in starts]
        boot = np.vstack(blocks)
        return boot[:n]

    def process(self, original_1m_candles: np.ndarray, out: np.ndarray) -> bool:
        # copy everything first (timestamps, volumes, etc)
        out[:] = original_1m_candles[:]
        n = len(out)
        # strictly positive floor to avoid invalid negative prices
        eps = 1e-12

        # compute the 3 deltas for each bar
        delta_close = np.diff(original_1m_candles[:, 2], prepend=self.last_price)
        delta_high  = original_1m_candles[:, 3] - original_1m_candles[:, 2]
        delta_low   = original_1m_candles[:, 2] - original_1m_candles[:, 4]

        # stack into shape (T, 3), skipping the first delta_close entry (prepend)
        deltas = np.column_stack([delta_close[1:], delta_high[1:], delta_low[1:]])

        # bootstrap blocks of the 3-tuples
        boot_deltas = self._bootstrap_blocks(deltas, n)

        # rebuild close prices (ensure strictly positive)
        boot_close = np.cumsum(boot_deltas[:, 0]) + self.last_price
        boot_close = np.maximum(boot_close, eps)
        out[:, 2] = boot_close

        # rebuild opens
        out[1:, 1] = boot_close[:-1]
        out[0, 1] = max(self.last_price, eps)

        # rebuild high and low from the bootstrapped ranges
        out[:, 3] = boot_close + boot_deltas[:, 1]
        out[:, 4] = boot_close - boot_deltas[:, 2]

        # enforce the true high/low bounds and positivity
        out[:, 1] = np.maximum(out[:, 1], eps)
        out[:, 2] = np.maximum(out[:, 2], eps)
        out[:, 3] = np.maximum.reduce([out[:, 1], out[:, 2], out[:, 3], out[:, 4]])
        out[:, 4] = np.minimum.reduce([out[:, 1], out[:, 2], out[:, 3], out[:, 4]])
        out[:, 4] = np.maximum(out[:, 4], eps)

        return True
