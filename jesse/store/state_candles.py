import threading

import numpy as np
from jesse.routes import router
import jesse.helpers as jh
from jesse.config import config
from jesse.enums import timeframes
from jesse.exceptions import RouteNotFound
from jesse.libs import DynamicNumpyArray


class _ThreadState(threading.local):
    execution_cutoff = None


class CandlesState:
    def __init__(self) -> None:
        self.storage = {}
        self.are_all_initiated = False
        self.initiated_pairs = {}
        # Historical timestamp replay derives forming candles from clock buckets;
        # live mode leaves this disabled and retains its streaming behavior.
        self.uses_timestamp_buckets = False
        # Direct simulator fixtures may omit warmup. Production loaders and
        # research requests enable this before enforcing configured route counts.
        self.enforce_warmup = False
        self._thread_state = _ThreadState()

    @property
    def execution_cutoff(self) -> int | None:
        """
        While live strategies run, the boundary they run for: candles that opened at or after
        it stay hidden. Strategies rely on it to run on closed candles: a late run can find the
        next candle started, and on exchanges without a candle stream an on-time run can too,
        as a trade starts its candle right at the boundary. Only the thread that set it sees
        it, as the threads adding candles must keep reading the latest one.
        """
        return self._thread_state.execution_cutoff

    @execution_cutoff.setter
    def execution_cutoff(self, timestamp: int | None) -> None:
        self._thread_state.execution_cutoff = timestamp

    def mark_all_as_initiated(self) -> None:
        for k in self.initiated_pairs:
            self.initiated_pairs[k] = True
        self.are_all_initiated = True

    def get_storage(self, exchange: str, symbol: str, timeframe: str) -> DynamicNumpyArray:
        # inline jh.key() — this is called multiple times per simulated minute
        try:
            return self.storage[f'{exchange}-{symbol}-{timeframe}']
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
        # inline jh.key() — this is on the hot path of every indicator call
        long_key = f'{exchange}-{symbol}-{timeframe}'
        short_key = f'{exchange}-{symbol}-1m'
        required_1m_to_complete_count = jh.timeframe_to_one_minutes(timeframe)
        current_1m_count = len(self.get_storage(exchange, symbol, '1m'))
        dif = current_1m_count % required_1m_to_complete_count
        return dif, long_key, short_key
