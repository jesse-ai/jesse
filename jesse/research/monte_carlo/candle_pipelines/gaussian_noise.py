import numpy as np
from typing import Optional

import jesse.helpers as jh
from .base_candles import BaseCandlesPipeline


class GaussianNoiseCandlesPipeline(BaseCandlesPipeline):

    def __init__(self, batch_size: int, *,
                 close_mu: float = 0.0,
                 close_sigma: Optional[float] = None,
                 high_mu: float = 0.0,
                 high_sigma: Optional[float] = None,
                 low_mu: float = 0.0,
                 low_sigma: Optional[float] = None,
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
        closes = original_1m_candles[:, 2]
        highs = original_1m_candles[:, 3]
        lows = original_1m_candles[:, 4]
        med_price = float(np.nan_to_num(np.median(closes), nan=0.0))

        # derive default sigmas when not provided
        if self.close_sigma is None:
            if n >= 2:
                rel_returns = np.diff(closes) / np.maximum(closes[:-1], eps)
                close_ret_std = float(np.nan_to_num(np.std(rel_returns), nan=0.0))
            else:
                close_ret_std = 0.0
            if close_ret_std == 0.0:
                # fallback: small fraction of median price (~0.05%)
                sigma_close = max(med_price * 0.0005, eps)
            else:
                sigma_close = max(close_ret_std * med_price, eps)
        else:
            sigma_close = self.close_sigma

        if self.high_sigma is None:
            high_spread_ratio = np.maximum(highs - closes, 0) / np.maximum(closes, eps)
            high_spread_std = float(np.nan_to_num(np.std(high_spread_ratio), nan=0.0))
            if high_spread_std == 0.0:
                sigma_high = max(med_price * 0.0005, eps)
            else:
                sigma_high = max(high_spread_std * med_price, eps)
        else:
            sigma_high = self.high_sigma

        if self.low_sigma is None:
            low_spread_ratio = np.maximum(closes - lows, 0) / np.maximum(closes, eps)
            low_spread_std = float(np.nan_to_num(np.std(low_spread_ratio), nan=0.0))
            if low_spread_std == 0.0:
                sigma_low = max(med_price * 0.0005, eps)
            else:
                sigma_low = max(low_spread_std * med_price, eps)
        else:
            sigma_low = self.low_sigma

        # close price
        noise = np.random.normal(self.close_mu, sigma_close, size=n).cumsum()
        out[:, 2] = np.maximum(out[:, 2] + noise, eps)

        # open price
        out[1:, 1] = out[:-1, 2]
        out[0, 1] = max(last_price, eps)

        # high
        high_std = 0.0 if sigma_high == 0.0 else np.random.normal(0, sigma_high, size=n)
        out[:, 3] = out[:, 3] + self.high_mu + high_std

        # low
        low_std = 0.0 if sigma_low == 0.0 else np.random.normal(0, sigma_low, size=n)
        out[:, 4] = out[:, 4] + self.low_mu + low_std

        # enforce bounds and positivity
        out[:, 1] = np.maximum(out[:, 1], eps)
        out[:, 2] = np.maximum(out[:, 2], eps)
        out[:, 3] = np.maximum(np.maximum(out[:, 1], out[:, 2]), np.maximum(out[:, 3], out[:, 4]))
        out[:, 4] = np.minimum(np.minimum(out[:, 1], out[:, 2]), np.minimum(out[:, 3], out[:, 4]))
        out[:, 4] = np.maximum(out[:, 4], eps)

        return True
