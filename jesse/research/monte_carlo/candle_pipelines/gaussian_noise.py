import numpy as np

import jesse.helpers as jh
from .base_candles import BaseCandlesPipeline


class GaussianNoiseCandlesPipeline(BaseCandlesPipeline):

    def __init__(self, batch_size: int, *,
                 close_mu: float = 0.0,
                 close_sigma: float,
                 high_mu: float = 0.0,
                 high_sigma: float,
                 low_mu: float = 0.0,
                 low_sigma: float,
                 ) -> None:
        """
        Add gaussian noise to candles
        """
        super().__init__(batch_size)
        self._first_time = True
        self.close_mu = close_mu
        self.close_sigma = close_sigma
        self.high_mu = high_mu
        self.high_sigma = high_sigma
        self.low_mu = low_mu
        self.low_sigma = low_sigma

    def process(self, original_1m_candles: np.ndarray, out: np.ndarray) -> bool:
        eps = 1e-12
        if not self._first_time:
            last_price = out[-1, 2]  # last_close_price
        else:
            self._first_time = False
            # in case we don't have history set the price as the first price so the bias will be 0
            last_price = original_1m_candles[0, 1]
        out[:] = original_1m_candles[:]

        n = len(out)

        # close price
        noise = np.random.normal(self.close_mu, self.close_sigma, size=n).cumsum()
        out[:, 2] = np.maximum(out[:, 2] + noise, eps)

        # open price
        out[1:, 1] = out[:-1, 2]
        out[0, 1] = max(last_price, eps)

        # high
        high_std = 0.0 if self.high_sigma == 0.0 else np.random.normal(0, self.high_sigma, size=n)
        out[:, 3] = out[:, 3] + self.high_mu + high_std

        # low
        low_std = 0.0 if self.low_sigma == 0.0 else np.random.normal(0, self.low_sigma, size=n)
        out[:, 4] = out[:, 4] + self.low_mu + low_std

        # enforce bounds and positivity
        out[:, 1] = np.maximum(out[:, 1], eps)
        out[:, 2] = np.maximum(out[:, 2], eps)
        out[:, 3] = np.maximum(np.maximum(out[:, 1], out[:, 2]), np.maximum(out[:, 3], out[:, 4]))
        out[:, 4] = np.minimum(np.minimum(out[:, 1], out[:, 2]), np.minimum(out[:, 3], out[:, 4]))
        out[:, 4] = np.maximum(out[:, 4], eps)

        return True
