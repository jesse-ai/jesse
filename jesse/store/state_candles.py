import numpy as np
from jesse.routes import router
import jesse.helpers as jh
from jesse.config import config
from jesse.enums import timeframes
from jesse.exceptions import RouteNotFound
from jesse.libs import DynamicNumpyArray


class CandlesState:
    def __init__(self) -> None:
        self.storage = {}
        self.are_all_initiated = False
        self.initiated_pairs = {}

    def mark_all_as_initiated(self) -> None:
        for k in self.initiated_pairs:
            self.initiated_pairs[k] = True
        self.are_all_initiated = True

    def get_storage(self, exchange: str, symbol: str, timeframe: str) -> DynamicNumpyArray:
        key = jh.key(exchange, symbol, timeframe)

        try:
            return self.storage[key]
        except KeyError:
            raise RouteNotFound(symbol, timeframe)

    def init_storage(self, bucket_size: int = 1000) -> None:
        for r in router.all_formatted_routes:
            exchange, symbol = r['exchange'], r['symbol']

            # initiate the '1m' timeframes
            key = jh.key(exchange, symbol, timeframes.MINUTE_1)
            self.storage[key] = DynamicNumpyArray((bucket_size, 6))

            for timeframe in config['app']['considering_timeframes']:
                key = jh.key(exchange, symbol, timeframe)
                # ex: 1440 / 60 + 1 (reserve one for forming candle)
                total_bigger_timeframe = int((bucket_size / jh.timeframe_to_one_minutes(timeframe)) + 1)
                self.storage[key] = DynamicNumpyArray((total_bigger_timeframe, 6))


    def forming_estimation(self, exchange: str, symbol: str, timeframe: str) -> tuple:
        long_key = jh.key(exchange, symbol, timeframe)
        short_key = jh.key(exchange, symbol, '1m')
        required_1m_to_complete_count = jh.timeframe_to_one_minutes(timeframe)
        current_1m_count = len(self.get_storage(exchange, symbol, '1m'))
        dif = current_1m_count % required_1m_to_complete_count
        return dif, long_key, short_key
