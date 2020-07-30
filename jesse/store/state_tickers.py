import numpy as np

import jesse.helpers as jh
from jesse.config import config
from jesse.libs import DynamicNumpyArray
from jesse.models import store_ticker_into_db


class TickersState:
    """

    """
    def __init__(self):
        self.storage = {}

    def init_storage(self):
        for c in config['app']['considering_candles']:
            key = jh.key(c[0], c[1])
            self.storage[key] = DynamicNumpyArray((60, 5), drop_at=120)

    def add_ticker(self, ticker: np.ndarray, exchange: str, symbol: str):
        """

        :param ticker:
        :param exchange:
        :param symbol:
        :return:
        """
        key = jh.key(exchange, symbol)

        # only process once per second
        if len(self.storage[key][:]) == 0 or jh.now() - self.storage[key][-1][0] >= 1000:
            self.storage[key].append(ticker)

            if jh.is_collecting_data():
                store_ticker_into_db(exchange, symbol, ticker)
                return

    def get_tickers(self, exchange: str, symbol: str):
        """

        :param exchange:
        :param symbol:
        :return:
        """
        key = jh.key(exchange, symbol)
        return self.storage[key][:]

    def get_current_ticker(self, exchange: str, symbol: str):
        """

        :param exchange:
        :param symbol:
        :return:
        """
        key = jh.key(exchange, symbol)
        return self.storage[key][-1]

    def get_past_ticker(self, exchange: str, symbol: str, number_of_tickers_ago: int):
        """

        :param exchange:
        :param symbol:
        :param number_of_tickers_ago:
        :return:
        """
        if number_of_tickers_ago > 120:
            raise ValueError('Max accepted value for number_of_tickers_ago is 120')

        number_of_tickers_ago = abs(number_of_tickers_ago)
        key = jh.key(exchange, symbol)
        return self.storage[key][-1 - number_of_tickers_ago]
