import numpy as np
from typing import Optional

from .base_candles import BaseCandlesPipeline


class GaussianResamplerCandlesPipeline(BaseCandlesPipeline):

    def __init__(self, batch_size: int, *,
                 mu: float = 0.0, sigma: Optional[float] = None,
                 ) -> None:
        """
        Add gaussian noise to candles
        """
        super().__init__(batch_size)
        self.mu = mu
        self.sigma = sigma

    def process(self, original_1m_candles: np.ndarray, out: np.ndarray) -> bool:
        eps = 1e-12
        out[:] = original_1m_candles[:]

        # close price
        closes = original_1m_candles[:, 2]
        n = len(out)
        med_price = float(np.nan_to_num(np.median(closes), nan=0.0))

        delta_close = np.diff(closes, prepend=self.last_price)
        mu_delta = float(np.nan_to_num(np.mean(delta_close[1:]), nan=0.0))
        sigma_delta_close = float(np.nan_to_num(np.std(delta_close[1:]), nan=0.0))

        # derive scale factor from relative returns if sigma is not provided
        if self.sigma is None:
            if n >= 2:
                rel_returns = np.diff(closes) / np.maximum(closes[:-1], eps)
                ret_std = float(np.nan_to_num(np.std(rel_returns), nan=0.0))
            else:
                ret_std = 0.0
            target_abs_close_std = max((ret_std * med_price) if ret_std > 0.0 else (med_price * 0.0005), eps)
            scale_factor = target_abs_close_std / max(sigma_delta_close, eps)
        else:
            scale_factor = self.sigma

        std_close = sigma_delta_close * scale_factor
        # debug the effective parameters used for the close process
        out[:, 2] = np.random.normal(mu_delta + self.mu, std_close, size=n).cumsum() + self.last_price
        out[:, 2] = np.maximum(out[:, 2], eps)

        # open price
        out[1:, 1] = out[:-1, 2]
        out[0, 1] = max(self.last_price, eps)

        # high
        delta_high_close = original_1m_candles[:, 3] - original_1m_candles[:, 2]
        mu_delta = float(np.nan_to_num(np.mean(delta_high_close), nan=0.0))
        sigma_delta_high = float(np.nan_to_num(np.std(delta_high_close), nan=0.0))
        std_high = sigma_delta_high * scale_factor
        out[:, 3] = out[:, 2] + np.random.normal(mu_delta + self.mu, std_high, size=n)

        delta_close_low = original_1m_candles[:, 2] - original_1m_candles[:, 4]
        mu_delta = float(np.nan_to_num(np.mean(delta_close_low), nan=0.0))
        sigma_delta_low = float(np.nan_to_num(np.std(delta_close_low), nan=0.0))
        std_low = sigma_delta_low * scale_factor
        out[:, 4] = out[:, 2] - np.random.normal(mu_delta + self.mu, std_low, size=n)

        # enforce bounds and positivity
        out[:, 1] = np.maximum(out[:, 1], eps)
        out[:, 2] = np.maximum(out[:, 2], eps)
        out[:, 3] = np.maximum(np.maximum(out[:, 1], out[:, 2]), np.maximum(out[:, 3], out[:, 4]))
        out[:, 4] = np.minimum(np.minimum(out[:, 1], out[:, 2]), np.minimum(out[:, 3], out[:, 4]))
        out[:, 4] = np.maximum(out[:, 4], eps)

        return True
