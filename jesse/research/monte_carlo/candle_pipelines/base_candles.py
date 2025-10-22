import numpy as np


class BaseCandlesPipeline:
    def __init__(self, batch_size: int) -> None:
        self._batch_size = batch_size
        self._output: np.ndarray = np.zeros((batch_size, 6))
        self.last_price = 0.0

    def get_candles(self, candles: np.ndarray, index: int, candles_step: int = -1) -> np.ndarray:
        index = index % self._batch_size
        if index == 0:
            if self.last_price == 0.0:
                self.last_price = candles[0, 1]  # the first time use open price instead of last close
            else:
                self.last_price = self._output[-1, 2]  # later use the last_price
            inject_candle = self.process(candles, self._output[:len(candles)])
            if not inject_candle:
                self._output[:] = candles
        if candles_step == -1:
            return self._output[index]
        if index + candles_step <= self._batch_size:
            return self._output[index:index + candles_step]
        raise ValueError("Batch size to candle pipeline supported only multiplication of the minimum timeframe in your"
                         " routes.")

    def process(self, original_1m_candles: np.ndarray, out: np.ndarray) -> bool:
        """
        :param original_1m_candles: get original 1m candles to modify it for research purposes to test various scenarios.
            Get the next `batch_size` 1m candles.
        :param out: The candles that will be injected to the simulation instead of the original 1m candles.
            Contains the previous batch.
        :return: True if out is modified, False otherwise
        """
        return False

