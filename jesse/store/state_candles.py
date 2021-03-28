import numpy as np

import jesse.helpers as jh
import jesse.services.selectors as selectors
from jesse.config import config
from jesse.enums import timeframes
from jesse.exceptions import RouteNotFound
from jesse.libs import DynamicNumpyArray
from jesse.models import store_candle_into_db
from jesse.services.candle import generate_candle_from_one_minutes


class CandlesState:
    def __init__(self) -> None:
        self.storage = {}
        self.is_initiated = False

    def get_storage(self, exchange: str, symbol: str, timeframe: str):
        key = jh.key(exchange, symbol, timeframe)

        try:
            return self.storage[key]
        except KeyError:
            raise RouteNotFound(
                f"Bellow route is required but missing in your routes:\n('{exchange}', '{symbol}', '{timeframe}')"
            )

    def init_storage(self, bucket_size: int = 1000) -> None:
        for c in config['app']['considering_candles']:
            exchange, symbol = c[0], c[1]

            # initiate the '1m' timeframes
            key = jh.key(exchange, symbol, timeframes.MINUTE_1)
            self.storage[key] = DynamicNumpyArray((bucket_size, 6))

            for timeframe in config['app']['considering_timeframes']:
                key = jh.key(exchange, symbol, timeframe)
                # ex: 1440 / 60 + 1 (reserve one for forming candle)
                total_bigger_timeframe = int((bucket_size / jh.timeframe_to_one_minutes(timeframe)) + 1)
                self.storage[key] = DynamicNumpyArray((total_bigger_timeframe, 6))

    def add_candle(
            self,
            candle: np.ndarray,
            exchange: str,
            symbol: str,
            timeframe: str,
            with_execution: bool = True,
            with_generation: bool = True,
            is_forming_candle: bool = False
    ) -> None:
        if jh.is_collecting_data():
            # make sure it's a complete (and not a forming) candle
            if jh.now_to_timestamp() >= (candle[0] + 60000):
                store_candle_into_db(exchange, symbol, candle)
            return

        arr: DynamicNumpyArray = self.get_storage(exchange, symbol, timeframe)

        if jh.is_live():
            self.update_position(exchange, symbol, candle)
        # initial
        if len(arr) == 0:
            arr.append(candle)

        # if it's new, add
        elif candle[0] > arr[-1][0]:
            # in paper mode, check to see if the new candle causes any active orders to be executed
            if with_execution and jh.is_paper_trading():
                self.simulate_order_execution(exchange, symbol, timeframe, candle)

            arr.append(candle)

            # generate other timeframes
            if with_generation and timeframe == '1m':
                self.generate_bigger_timeframes(candle, exchange, symbol, with_execution, is_forming_candle)

        # if it's the last candle again, update
        elif candle[0] == arr[-1][0]:
            # in paper mode, check to see if the new candle causes any active orders to get executed
            if with_execution and jh.is_paper_trading():
                self.simulate_order_execution(exchange, symbol, timeframe, candle)

            arr[-1] = candle

            # regenerate other timeframes
            if with_generation and timeframe == '1m':
                self.generate_bigger_timeframes(candle, exchange, symbol, with_execution, is_forming_candle)

        # past candles will be ignored (dropped)
        elif candle[0] < arr[-1][0]:
            return

    @staticmethod
    def update_position(exchange: str, symbol: str, candle: np.ndarray) -> None:
        # get position object
        p = selectors.get_position(exchange, symbol)

        # for extra_route candles, p == None, hence no further action is required
        if p is None:
            return

        # update position.current_price
        p.current_price = jh.round_price_for_live_mode(candle[2], candle[2])

    def generate_bigger_timeframes(self, candle: np.ndarray, exchange: str, symbol: str, with_execution: bool,
                                   is_forming_candle: bool) -> None:
        if not jh.is_live():
            return

        for timeframe in config['app']['considering_timeframes']:
            # skip '1m'
            if timeframe == '1m':
                continue

            last_candle = self.get_current_candle(exchange, symbol, timeframe)
            generate_from_count = int((candle[0] - last_candle[0]) / 60_000)
            required_for_complete_candle = jh.timeframe_to_one_minutes(timeframe)
            short_candles = self.get_candles(exchange, symbol, '1m')[-1 - generate_from_count:]
            if generate_from_count == (required_for_complete_candle - 1) and not is_forming_candle:
                is_forming_candle = False
            else:
                is_forming_candle = True

            # update latest candle
            generated_candle = generate_candle_from_one_minutes(
                timeframe,
                short_candles,
                True
            )

            self.add_candle(generated_candle, exchange, symbol, timeframe, with_execution, with_generation=False,
                            is_forming_candle=is_forming_candle)

    def simulate_order_execution(self, exchange: str, symbol: str, timeframe: str, new_candle: np.ndarray) -> None:
        previous_candle = self.get_current_candle(exchange, symbol, timeframe)
        orders = selectors.get_orders(exchange, symbol)

        if previous_candle[2] == new_candle[2]:
            return

        for o in orders:
            # skip inactive orders
            if not o.is_active:
                continue

            if ((o.price >= previous_candle[2]) and (o.price <= new_candle[2])) or (
                    (o.price <= previous_candle[2]) and (o.price >= new_candle[2])):
                o.execute()

    def batch_add_candle(self, candles: np.ndarray, exchange: str, symbol: str, timeframe: str,
                         with_generation: bool = True) -> None:
        for c in candles:
            self.add_candle(c, exchange, symbol, timeframe, with_execution=False, with_generation=with_generation)

    def forming_estimation(self, exchange: str, symbol: str, timeframe: str) -> tuple:
        long_key = jh.key(exchange, symbol, timeframe)
        short_key = jh.key(exchange, symbol, '1m')
        required_1m_to_complete_count = jh.timeframe_to_one_minutes(timeframe)
        current_1m_count = len(self.get_storage(exchange, symbol, '1m'))

        dif = current_1m_count % required_1m_to_complete_count
        return dif, long_key, short_key

    # # # # # # # # #
    # # # # # getters
    # # # # # # # # #
    def get_candles(self, exchange: str, symbol: str, timeframe: str) -> np.ndarray:
        # no need to worry for forming candles when timeframe == 1m
        if timeframe == '1m':
            arr: DynamicNumpyArray = self.get_storage(exchange, symbol, '1m')
            if len(arr) == 0:
                return np.zeros((0, 6))
            else:
                return arr[:]

        # other timeframes
        dif, long_key, short_key = self.forming_estimation(exchange, symbol, timeframe)
        long_count = len(self.get_storage(exchange, symbol, timeframe))
        short_count = len(self.get_storage(exchange, symbol, '1m'))

        if dif == 0 and long_count == 0:
            return np.zeros((0, 6))

        # complete candle
        if dif == 0 or self.storage[long_key][:long_count][-1][0] == self.storage[short_key][short_count - dif][0]:
            return self.storage[long_key][:long_count]
        # generate forming
        else:
            return np.concatenate(
                (
                    self.storage[long_key][:long_count],
                    np.array(
                        (
                            generate_candle_from_one_minutes(
                                timeframe,
                                self.storage[short_key][short_count - dif:short_count],
                                True
                            ),
                        )
                    )
                ), axis=0
            )

    def get_current_candle(self, exchange: str, symbol: str, timeframe: str) -> np.ndarray:
        # no need to worry for forming candles when timeframe == 1m
        if timeframe == '1m':
            arr: DynamicNumpyArray = self.get_storage(exchange, symbol, '1m')
            if len(arr) == 0:
                return np.zeros((0, 6))
            else:
                return arr[-1]

        # other timeframes
        dif, long_key, short_key = self.forming_estimation(exchange, symbol, timeframe)
        long_count = len(self.get_storage(exchange, symbol, timeframe))
        short_count = len(self.get_storage(exchange, symbol, '1m'))

        # complete candle
        if dif == 0:
            if long_count == 0:
                return np.zeros((0, 6))
            else:
                return self.storage[long_key][-1]
        # generate forming
        else:
            return generate_candle_from_one_minutes(
                timeframe, self.storage[short_key][short_count - dif:short_count],
                True
            )
