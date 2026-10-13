import numpy as np
from .base_candles import BaseCandlesPipeline


class MovingBlockBootstrapCandlesPipeline(BaseCandlesPipeline):
    def __init__(self, batch_size: int, seed: int = None, **_ignored) -> None:
        """
        Generate synthetic candles by moving-block bootstrap on multivariate
        tuples of (close log-return, relative high range, relative low range).

        Resampling is done in relative (multiplicative) terms so a block keeps
        each bar's percentage move no matter which price level it is replayed
        at. Absolute-dollar deltas let a block from a high-price regime replayed
        at a low price drag the cumulative sum through zero, pinning the whole
        path at the positivity floor (jesse-ai/jesse#630).

        Parameters
        ----------
        batch_size : int
            Size of the internal regeneration buffer in minutes. The pipeline
            derives a reasonable bootstrap block length from this, so there is
            no separate block-size argument.
        seed : int, optional
            Seed for the internal RNG. Leave None for independent random
            scenarios (the normal case); pass an int for reproducible output
            (used by tests asserting the fast and full simulators are identical).
        """
        super().__init__(batch_size)

        # Derive block size from batch size. Heuristic: max(10, batch_size // 10),
        # then clamp to [1, batch_size - 1]. This preserves short-horizon
        # dependence while allowing variety.
        derived_block_size = max(10, batch_size // 10)
        derived_block_size = max(1, min(batch_size - 1, derived_block_size))
        self._block_size = derived_block_size

        # Independent RNG per pipeline instance to avoid identical scenarios
        # (seedable for reproducible tests).
        self._rng = np.random.default_rng(seed)

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
        # strictly positive floor to avoid invalid prices from degenerate input;
        # valid paths now stay positive by construction (see the rebuild below)
        eps = 1e-12

        closes = original_1m_candles[:, 2]
        # Guard the log bases: prices are strictly positive in valid data, but a
        # non-positive close would otherwise turn the returns into -inf/nan.
        safe_closes = np.maximum(closes, eps)
        base_price = self.last_price if self.last_price > 0 else safe_closes[0]

        # compute the 3 relative deltas for each bar
        delta_close = np.diff(np.log(safe_closes), prepend=np.log(base_price))
        rel_high = (original_1m_candles[:, 3] - safe_closes) / safe_closes
        rel_low = (safe_closes - original_1m_candles[:, 4]) / safe_closes

        # stack into shape (T, 3), skipping the first delta_close entry (prepend)
        deltas = np.column_stack([delta_close[1:], rel_high[1:], rel_low[1:]])

        # bootstrap blocks of the 3-tuples
        boot_deltas = self._bootstrap_blocks(deltas, n)

        # rebuild close prices by multiplication, so positivity holds by construction
        boot_close = base_price * np.exp(np.cumsum(boot_deltas[:, 0]))
        out[:, 2] = boot_close

        # rebuild opens
        out[1:, 1] = boot_close[:-1]
        out[0, 1] = base_price

        # rebuild high and low from the bootstrapped relative ranges
        out[:, 3] = boot_close * (1 + boot_deltas[:, 1])
        out[:, 4] = boot_close * (1 - boot_deltas[:, 2])

        # enforce the true high/low bounds and positivity
        out[:, 1] = np.maximum(out[:, 1], eps)
        out[:, 2] = np.maximum(out[:, 2], eps)
        out[:, 3] = np.maximum.reduce([out[:, 1], out[:, 2], out[:, 3], out[:, 4]])
        out[:, 4] = np.minimum.reduce([out[:, 1], out[:, 2], out[:, 3], out[:, 4]])
        out[:, 4] = np.maximum(out[:, 4], eps)

        return True
