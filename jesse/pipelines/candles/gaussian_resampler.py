import numpy as np

from jesse.pipelines.candles import BaseCandlesPipeline


class GaussianResamplerCandlesPipeline(BaseCandlesPipeline):

    def __init__(self, batch_size: int, *,
                 mu: float = 0.0, sigma: float = 1.0,
                 ) -> None:
        """
        Add gaussian noise to candles
        """
        super().__init__(batch_size)
        self.mu = mu
        self.sigma = sigma

    def process(self, original_1m_candles: np.ndarray, out: np.ndarray) -> bool:
        out[:] = original_1m_candles[:]

        # close price
        delta_close = np.diff(original_1m_candles[:, 2], prepend=self.last_price)
        mu_delta = np.mean(delta_close[1:])
        sigma_delta = np.std(delta_close[1:])
        out[:, 2] = np.random.normal(mu_delta + self.mu, sigma_delta * self.sigma, size=len(out)).cumsum() + self.last_price

        # open price
        out[1:, 1] = out[:-1, 2]
        out[0, 1] = self.last_price

        # high
        delta_high_close = original_1m_candles[:, 3] - original_1m_candles[:, 2]
        mu_delta = np.mean(delta_high_close)
        sigma_delta = np.std(delta_high_close)
        out[:, 3] = out[:, 2] + np.random.normal(mu_delta + self.mu, sigma_delta * self.sigma, size=len(out))

        delta_close_low = original_1m_candles[:, 2] - original_1m_candles[:, 4]
        mu_delta = np.mean(delta_close_low)
        sigma_delta = np.std(delta_close_low)
        out[:, 4] = out[:, 2] - np.random.normal(mu_delta + self.mu, sigma_delta * self.sigma, size=len(out))

        out[:, 3] = np.maximum(np.maximum(out[:, 1], out[:, 2]), np.maximum(out[:, 3], out[:, 4]))
        out[:, 4] = np.minimum(np.minimum(out[:, 1], out[:, 2]), np.minimum(out[:, 3], out[:, 4]))

        return True
