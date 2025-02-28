import math

import numpy as np

from jesse.pipelines.candles import BaseCandlesPipeline


class MultipleCandlesPipeline(BaseCandlesPipeline):

    def __init__(self, *pipelines: BaseCandlesPipeline):
        batch_size = math.lcm(*[pipeline._batch_size for pipeline in pipelines])
        super().__init__(batch_size)
        self.pipelines = pipelines

    def process(self, original_1m_candles: np.ndarray, out: np.ndarray) -> bool:
        for pipeline in self.pipelines:
            self.pipeline_process(pipeline, original_1m_candles, out)
        return True

    @staticmethod
    def pipeline_process(pipeline: BaseCandlesPipeline, input_candles: np.ndarray, out: np.ndarray) -> None:
        batch_size = pipeline._batch_size
        for i in range(0, len(input_candles), batch_size):
            candles = input_candles[i:i + batch_size]
            output = pipeline.get_candles(candles, 0, len(candles))
            out[i:i + len(output)] = output
