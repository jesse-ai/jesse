import requests

import jesse.helpers as jh
from jesse import exceptions
from .interface import CandleExchange


class Binance(CandleExchange):
    def __init__(self) -> None:
        super().__init__('Binance', 1000, 0.5)
        self.endpoint = 'https://www.binance.com/api/v1/klines'

    def init_backup_exchange(self):
        self.backup_exchange = None

    def get_starting_time(self, symbol):
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
        first_timestamp = int(data[0][0])
        second_timestamp = first_timestamp + 60_000 * 1440

        return second_timestamp

    def fetch(self, symbol, start_timestamp):
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

        data = response.json()

        # Exchange In Maintenance
        if response.status_code == 502:
            raise exceptions.ExchangeInMaintenance('ERROR: 502 Bad Gateway. Please try again later')

        # unsupported symbol
        if response.status_code == 400:
            raise ValueError(response.json()['msg'])

        candles = []

        for d in data:
            candles.append({
                'id': jh.generate_unique_id(),
                'symbol': symbol,
                'exchange': self.name,
                'timestamp': int(d[0]),
                'open': float(d[1]),
                'close': float(d[4]),
                'high': float(d[2]),
                'low': float(d[3]),
                'volume': float(d[5])
            })

        return candles
