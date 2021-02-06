import requests

import jesse.helpers as jh
from jesse import exceptions
from .interface import CandleExchange


class Coinbase(CandleExchange):
    def __init__(self) -> None:
        super().__init__('Coinbase', 300, 0.6)
        self.endpoint = 'https://api.pro.coinbase.com/products'

    def init_backup_exchange(self):
        from .bitfinex import Bitfinex
        self.backup_exchange = Bitfinex()

    def get_starting_time(self, symbol: str):
        """
        Because Coinbase's API sucks and does not make this take easy for us,
        we do it manually for as much symbol as we can!

        :param symbol: str
        :return: int
        """
        if symbol == 'BTC-USD':
            return 1438387200000
        elif symbol == 'ETH-USD':
            return 1464739200000
        elif symbol == 'LTC-USD':
            return 1477958400000

        return None

    def fetch(self, symbol: str, start_timestamp: int):
        """
        note1: unlike Bitfinex, Binance does NOT skip candles with volume=0.
        note2: like Bitfinex, start_time includes the candle and so does the end_time.
        """
        end_timestamp = start_timestamp + (self.count - 1) * 60000

        payload = {
            'granularity': '60',
            'start': jh.timestamp_to_time(start_timestamp),
            'end': jh.timestamp_to_time(end_timestamp),
        }

        response = requests.get(
            self.endpoint + '/{}/candles'.format(symbol),
            params=payload
        )

        self._handle_errors(response)

        data = response.json()
        candles = []

        for d in data:
            candles.append({
                'id': jh.generate_unique_id(),
                'symbol': symbol,
                'exchange': self.name,
                'timestamp': int(d[0]) * 1000,
                'open': float(d[3]),
                'close': float(d[4]),
                'high': float(d[2]),
                'low': float(d[1]),
                'volume': float(d[5])
            })

        return candles

    @staticmethod
    def _handle_errors(response):
        # Exchange In Maintenance
        if response.status_code == 502:
            raise exceptions.ExchangeInMaintenance('ERROR: 502 Bad Gateway. Please try again later')

        # unsupported symbol
        if response.status_code == 404:
            raise ValueError(response.json()['message'])

        if response.status_code != 200:
            raise Exception(response.content)
