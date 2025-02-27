import numpy as np

from jesse.pipelines.candles import BaseCandlesPipeline


class RearrangeCandles(BaseCandlesPipeline):

    def __init__(self, batch_size: int) -> None:
        super().__init__(batch_size)

    def process(self, original_1m_candles: np.ndarray, out: np.ndarray) -> bool:
        out[:len(original_1m_candles), :] = original_1m_candles[:, :]

        out[:, 1] = out[:, 1] - out[:, 2]
        out[:, 3] = out[:, 3] - out[:, 2]
        out[:, 4] = out[:, 4] - out[:, 2]
        out[:, 2] = np.diff(out[:, 2], prepend=self.last_price)

        shuffled_indices = np.random.permutation(len(out))
        out[:] = out[shuffled_indices]
        out[:, 0] = original_1m_candles[:, 0]

        out[:, 2] = out[:, 2].cumsum() + self.last_price
        out[:, 1] += out[:, 2]
        out[:, 3] += out[:, 2]
        out[:, 4] += out[:, 2]

        return True
