import numpy as np

import jesse.helpers as jh
import jesse.services.selectors as selectors
from jesse.config import config
from jesse.enums import timeframes
from jesse.exceptions import RouteNotFound
from jesse.libs import DynamicNumpyArray
from jesse.models import store_candle_into_db
from jesse.services.candle import generate_candle_from_one_minutes
from timeloop import Timeloop
from datetime import timedelta
from jesse.services import logger


class CandlesState:
    def __init__(self) -> None:
        self.storage = {}
        self.are_all_initiated = False
        self.initiated_pairs = {}

    def generate_new_candles_loop(self) -> None:
        """
        to prevent the issue of missing candles when no volume is traded on the live exchange
        """
        t = Timeloop()

        @t.job(interval=timedelta(seconds=1))
        def time_loop_per_second():
            # make sure all candles are already initiated
            if not self.are_all_initiated:
                return

            # only at first second on each minute
            if jh.now() % 60_000 != 1000:
                return

            for c in selectors.get_all_routes():
                exchange, symbol, timeframe = c['exchange'], c['symbol'], c['timeframe']
                current_candle = self.get_current_candle(exchange, symbol, timeframe)

                # fix for a bug
                if current_candle[0] <= 60_000:
                    continue

                # if a missing candle is found, generate an empty candle from the
                # last one this is useful when the exchange doesn't stream an empty
                # candle when no volume is traded at the period of the candle
                if jh.next_candle_timestamp(current_candle, timeframe) < jh.now():
                    new_candle = self._generate_empty_candle_from_previous_candle(current_candle, timeframe=timeframe)
                    self.add_candle(new_candle, exchange, symbol, timeframe)

        t.start()

    @staticmethod
    def _generate_empty_candle_from_previous_candle(
            previous_candle: np.ndarray,
            timeframe: str = '1m'
    ) -> np.ndarray:
        new_candle = previous_candle.copy()
        candles_count = jh.timeframe_to_one_minutes(timeframe) * 60_000
        new_candle[0] = previous_candle[0] + candles_count

        # new candle's open, close, high, and low all equal to previous candle's close
        new_candle[1] = previous_candle[2]
        new_candle[2] = previous_candle[2]
        new_candle[3] = previous_candle[2]
        new_candle[4] = previous_candle[2]
        # set volume to 0
        new_candle[5] = 0
        return new_candle

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
        for ar in selectors.get_all_routes():
            exchange, symbol = ar['exchange'], ar['symbol']

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
            with_skip: bool = True
    ) -> None:
        if jh.is_collecting_data():
            raise NotImplemented("Collecting data is deactivated at the moment")
            # make sure it's a complete (and not a forming) candle
            # if jh.now_to_timestamp() >= (candle[0] + 60000):
            #     store_candle_into_db(exchange, symbol, candle)
            # return

        # overwrite with_generation based on the config value for live sessions
        if jh.is_live() and not jh.get_config('env.data.generate_candles_from_1m'):
            with_generation = False

        if candle[0] == 0:
            if jh.is_debugging():
                logger.error(
                    f"DEBUGGING-VALUE: please report to Saleh: candle[0] is zero. \nFull candle: {candle}\n"
                )
            return

        arr: DynamicNumpyArray = self.get_storage(exchange, symbol, timeframe)

        if jh.is_live():
            # ignore if candle is still being initially imported
            if with_skip and f'{exchange}-{symbol}' not in self.initiated_pairs:
                return

            # if it's not an old candle, update the related position's current_price
            if jh.next_candle_timestamp(candle, timeframe) > jh.now():
                self.update_position(exchange, symbol, candle[2])

            # ignore new candle at the time of execution because it messes
            # the count of candles without actually having an impact
            if candle[0] >= jh.now():
                return

            self._store_or_update_candle_into_db(exchange, symbol, timeframe, candle)

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
                self.generate_bigger_timeframes(candle, exchange, symbol, with_execution)

        # if it's the last candle again, update
        elif candle[0] == arr[-1][0]:
            # in paper mode, check to see if the new candle causes any active orders to get executed
            if with_execution and jh.is_paper_trading():
                self.simulate_order_execution(exchange, symbol, timeframe, candle)

            arr[-1] = candle

            # regenerate other timeframes
            if with_generation and timeframe == '1m':
                self.generate_bigger_timeframes(candle, exchange, symbol, with_execution)

        # allow updating of the previous candle.
        elif candle[0] < arr[-1][0]:
            # loop through the last 20 items in arr to find it. If so, update it.
            for i in range(max(20, len(arr) - 1)):
                if arr[-i][0] == candle[0]:
                    arr[-i] = candle
                    break
        else:
            logger.info(
                f"Could not find the candle with timestamp {jh.timestamp_to_time(candle[0])} in the storage. Last candle's timestamp: {jh.timestamp_to_time(arr[-1])}. timeframe: {timeframe}, exchange: {exchange}, symbol: {symbol}"
            )

    def _store_or_update_candle_into_db(self, exchange: str, symbol: str, timeframe: str, candle: np.ndarray) -> None:
        # if it's not an initial candle, add it to the storage, if already exists, update it
        if f'{exchange}-{symbol}' in self.initiated_pairs:
            store_candle_into_db(exchange, symbol, timeframe, candle, on_conflict='replace')

    def add_candle_from_trade(self, trade, exchange: str, symbol: str) -> None:
        """
        In few exchanges, there's no candle stream over the WS, for
        those we have to use cases the trades stream
        """
        if not jh.is_live():
            raise Exception('add_candle_from_trade() is for live modes only')

        # ignore if candle is still being initially imported
        if f'{exchange}-{symbol}' not in self.initiated_pairs:
            return

        # update position's current price
        self.update_position(exchange, symbol, trade['price'])

        def do(t):
            # in some cases we might be missing the current forming candle like it is on FTX, hence
            # if that is the case, generate the current forming candle (it won't be super accurate)
            current_candle = self.get_current_candle(exchange, symbol, t)
            if jh.next_candle_timestamp(current_candle, t) < jh.now():
                new_candle = self._generate_empty_candle_from_previous_candle(current_candle, t)
                self.add_candle(new_candle, exchange, symbol, t)

            current_candle = self.get_current_candle(exchange, symbol, t)

            new_candle = current_candle.copy()
            # close
            new_candle[2] = trade['price']
            # high
            new_candle[3] = max(new_candle[3], trade['price'])
            # low
            new_candle[4] = min(new_candle[4], trade['price'])
            # volume
            new_candle[5] += trade['volume']

            self.add_candle(new_candle, exchange, symbol, t)

        # to support both candle generation and ...
        if jh.get_config('env.data.generate_candles_from_1m'):
            do('1m')
        else:
            for ar in selectors.get_all_routes():
                if ar['exchange'] != exchange or ar['symbol'] != symbol:
                    return
                do(ar['timeframe'])

    @staticmethod
    def update_position(exchange: str, symbol: str, price: float) -> None:
        # get position object
        p = selectors.get_position(exchange, symbol)

        # for data_route candles, p == None, hence no further action is required
        if p is None:
            return

        if jh.is_live():
            price_precision = selectors.get_exchange(exchange).vars['precisions'][symbol]['price_precision']

            # update position.current_price
            p.current_price = jh.round_price_for_live_mode(price, price_precision)
        else:
            p.current_price = price

    def generate_bigger_timeframes(self, candle: np.ndarray, exchange: str, symbol: str, with_execution: bool) -> None:
        if not jh.is_live():
            return

        for timeframe in config['app']['considering_timeframes']:
            # skip '1m'
            if timeframe == '1m':
                continue

            last_candle = self.get_current_candle(exchange, symbol, timeframe)
            generate_from_count = int((candle[0] - last_candle[0]) / 60_000)
            number_of_candles = len(self.get_candles(exchange, symbol, '1m'))
            short_candles = self.get_candles(exchange, symbol, '1m')[-1 - generate_from_count:]

            if generate_from_count == -1:
                # it's receiving an slightly older candle than the last one. Ignore it
                return

            if generate_from_count < 0:
                current_1m = self.get_current_candle(exchange, symbol, '1m')
                raise ValueError(
                    f'generate_from_count cannot be negative! '
                    f'generate_from_count:{generate_from_count}, candle[0]:{candle[0]}, '
                    f'last_candle[0]:{last_candle[0]}, current_1m:{current_1m[0]}, number_of_candles:{number_of_candles}')

            if len(short_candles) == 0:
                raise ValueError(
                    f'No candles were passed. More info:'
                    f'\nexchange:{exchange}, symbol:{symbol}, timeframe:{timeframe}, generate_from_count:{generate_from_count}'
                    f'\nlast_candle\'s timestamp: {last_candle[0]}'
                    f'\ncurrent timestamp: {jh.now()}'
                )

            # update latest candle
            generated_candle = generate_candle_from_one_minutes(
                timeframe,
                short_candles,
                accept_forming_candles=True
            )

            self.add_candle(
                generated_candle, exchange, symbol, timeframe, with_execution, with_generation=False
            )

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

    def batch_add_candle(
            self,
            candles: np.ndarray,
            exchange: str,
            symbol: str,
            timeframe: str,
            with_generation: bool = True
    ) -> None:
        for c in candles:
            self.add_candle(c, exchange, symbol, timeframe, with_execution=False, with_generation=with_generation, with_skip=False)

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

        # forming candle
        if dif != 0:
            return generate_candle_from_one_minutes(
                timeframe, self.storage[short_key][short_count - dif:short_count],
                True
            )
        if long_count == 0:
            return np.zeros((0, 6))
        else:
            return self.storage[long_key][-1]

    def add_multiple_1m_candles(
        self,
        candles: np.ndarray,
        exchange: str,
        symbol: str,
    ) -> None:
        if not (jh.is_backtesting() or jh.is_optimizing()):
            raise Exception('add_multiple_1m_candles() is for backtesting or optimizing only')

        arr: DynamicNumpyArray = self.get_storage(exchange, symbol, '1m')

        # initial
        if len(arr) == 0:
            arr.append_multiple(candles)

        # if it's new, add
        elif candles[0, 0] > arr[-1][0]:
            arr.append_multiple(candles)

        # if it's the last candle again, update
        elif candles[0, 0] >= arr[-len(candles)][0] and candles[-1, 0] >= arr[-1][0]:
            override_candles = int(
                len(candles) - ((candles[-1, 0] - arr[-1][0]) / 60000)
            )
            arr[-override_candles:] = candles

        # Otherwise,it's true and error.
        else:
            raise IndexError(f"Could not find the candle with timestamp {jh.timestamp_to_time(candles[0, 0])} in the storage. Last candle's timestamp: {jh.timestamp_to_time(arr[-1][0])}. exchange: {exchange}, symbol: {symbol}")
