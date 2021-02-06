import requests

import jesse.helpers as jh
from jesse import exceptions
from .interface import CandleExchange


class TestnetBinanceFutures(CandleExchange):
    def __init__(self) -> None:
        super().__init__('Testnet Binance Futures', 1000, 0.5)
        self.endpoint = 'https://testnet.binancefuture.com/fapi/v1/klines'

    def init_backup_exchange(self):
        from .binance import Binance
        self.backup_exchange = Binance()

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
