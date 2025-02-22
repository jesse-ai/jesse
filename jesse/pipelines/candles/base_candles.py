import numpy as np


class BaseCandlesPipeline:
    def __init__(self, batch_size: int) -> None:
        self.batch_size = batch_size
        self.output: np.ndarray = np.zeros((batch_size, 6))

    def get_candles(self, candles: np.ndarray, index: int, candles_step: int = -1) -> np.ndarray:
        index = index % self.batch_size
        if index == 0:
            inject_candle = self.process(candles, self.output)
            if not inject_candle:
                self.output[:] = candles
        if candles_step == -1:
            return self.output[index]
        if index + candles_step <= self.batch_size:
            return self.output[index:index + candles_step]
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

