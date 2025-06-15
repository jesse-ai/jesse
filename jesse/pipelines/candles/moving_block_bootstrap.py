import numpy as np
from jesse.pipelines.candles import BaseCandlesPipeline

class MovingBlockBootstrapCandlesPipeline(BaseCandlesPipeline):
    def __init__(self, batch_size: int, *, block_size: int = 10) -> None:
        """
        Generate synthetic candles by moving-block bootstrap on multivariate 
        tuples of (delta_close, delta_high, delta_low).

        Args:
            batch_size: number of 1m bars to output.
            block_size: length of each bootstrap block (in bars).
        """
        super().__init__(batch_size)
        self.block_size = block_size

    def _bootstrap_blocks(self, arr: np.ndarray, n: int) -> np.ndarray:
        """
        Sample overlapping blocks of rows from `arr` to build a length-n output.
        `arr` is shape (T, 3) for the three deltas.
        """
        T, D = arr.shape
        if self.block_size > T:
            raise ValueError(f"block_size ({self.block_size}) > available data ({T})")
        max_start = T - self.block_size
        # how many blocks needed to reach n rows
        num_blocks = int(np.ceil(n / self.block_size)) + 1
        starts = np.random.randint(0, max_start + 1, size=num_blocks)
        blocks = [arr[s : s + self.block_size] for s in starts]
        boot = np.vstack(blocks)
        return boot[:n]

    def process(self, original_1m_candles: np.ndarray, out: np.ndarray) -> bool:
        # copy everything first (timestamps, volumes, etc)
        out[:] = original_1m_candles[:]
        n = len(out)

        # compute the 3 deltas for each bar
        delta_close = np.diff(original_1m_candles[:, 2], prepend=self.last_price)
        delta_high  = original_1m_candles[:, 3] - original_1m_candles[:, 2]
        delta_low   = original_1m_candles[:, 2] - original_1m_candles[:, 4]

        # stack into shape (T, 3), skipping the first delta_close entry (prepend)
        deltas = np.column_stack([delta_close[1:], delta_high[1:], delta_low[1:]])

        # bootstrap blocks of the 3-tuples
        boot_deltas = self._bootstrap_blocks(deltas, n)

        # rebuild close prices
        boot_close = np.cumsum(boot_deltas[:, 0]) + self.last_price
        out[:, 2] = boot_close

        # rebuild opens
        out[1:, 1] = boot_close[:-1]
        out[0, 1] = self.last_price

        # rebuild high and low from the bootstrapped ranges
        out[:, 3] = boot_close + boot_deltas[:, 1]
        out[:, 4] = boot_close - boot_deltas[:, 2]

        # enforce the true high/low bounds
        out[:, 3] = np.maximum.reduce([out[:,1], out[:,2], out[:,3], out[:,4]])
        out[:, 4] = np.minimum.reduce([out[:,1], out[:,2], out[:,3], out[:,4]])

        return True
