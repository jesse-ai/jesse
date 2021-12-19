import requests

import jesse.helpers as jh
from jesse import exceptions
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from typing import Union


class BinanceFutures(CandleExchange):
    def __init__(self) -> None:
        # import here instead of the top of the file to prevent possible the circular imports issue
        from jesse.modes.import_candles_mode.drivers.binance import Binance

        super().__init__(
            name='Binance Futures',
            count=1000,
            rate_limit_per_second=2,
            backup_exchange_class=Binance
        )

        self.endpoint = 'https://fapi.binance.com/fapi/v1/klines'

    def get_starting_time(self, symbol: str) -> int:
        dashless_symbol = jh.dashless_symbol(symbol)

        payload = {
            'interval': '1d',
            'symbol': dashless_symbol,
            'limit': 1500,
        }

        response = requests.get(self.endpoint, params=payload)

        # Exchange In Maintenance
        if response.status_code == 502:
            raise exceptions.ExchangeInMaintenance('ERROR: 502 Bad Gateway. Please try again later')

        # unsupported symbol
        if response.status_code == 400:
            raise ValueError(response.json()['msg'])

        if response.status_code != 200:
            raise Exception(response.content)

        data = response.json()

        # since the first timestamp doesn't include all the 1m
        # candles, let's start since the second day then
        first_timestamp = int(data[0][0])
        return first_timestamp + 60_000 * 1440

    def fetch(self, symbol: str, start_timestamp: int) -> Union[list, None]:
        """
        note1: unlike Bitfinex, Binance does NOT skip candles with volume=0.
        note2: like Bitfinex, start_time includes the candle and so does the end_time.
        """
        end_timestamp = start_timestamp + (self.count - 1) * 60000

        dashless_symbol = jh.dashless_symbol(symbol)

        payload = {
            'interval': '1m',
            'symbol': dashless_symbol,
            'startTime': start_timestamp,
            'endTime': end_timestamp,
            'limit': self.count,
        }

        response = requests.get(self.endpoint, params=payload)

        # Exchange In Maintenance
        if response.status_code == 502:
            raise exceptions.ExchangeInMaintenance('ERROR: 502 Bad Gateway. Please try again later')

        # unsupported symbol
        if response.status_code == 400:
            raise ValueError(response.json()['msg'])

        if response.status_code != 200:
            return

        data = response.json()
        return [{
            'id': jh.generate_unique_id(),
            'symbol': symbol,
            'exchange': self.name,
            'timestamp': int(d[0]),
            'open': float(d[1]),
            'close': float(d[4]),
            'high': float(d[2]),
            'low': float(d[3]),
            'volume': float(d[5])
        } for d in data]
