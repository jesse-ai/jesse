import requests

import jesse.helpers as jh
from jesse import exceptions
from .interface import CandleExchange


class Coincap(CandleExchange):

    def __init__(self):
        super().__init__('Coincap', 1440, 0.1)
        self.endpoint = 'https://api.coincap.io/v2/'

    def init_backup_exchange(self):
        from .coinbase import Coinbase
        self.backup_exchange = Coinbase()

    def get_starting_time(self, symbol: str):

        symbol_splited = symbol.split('-')


        baseId = self.find_symbol_id(symbol_splited[0])
        quoteId = self.find_symbol_id(symbol_splited[1])

        payload = {
            'interval': 'd1',
            'exchange': 'binance',
            'baseId': baseId,
            'quoteId': quoteId,

        }

        response = requests.get(self.endpoint + 'candles', params=payload)
        self._handle_errors(response)
        data = response.json()['data']

        # wrong symbol entered
        if not len(data):
            raise exceptions.SymbolNotFound(
                "No candle exists for {}. You're probably misspelling the symbol name.".format(symbol)
            )

        first_timestamp = int(data[0]['period'])
        second_timestamp = first_timestamp + 60_000 * 1440

        return second_timestamp

    def fetch(self, symbol, start_timestamp):

        end_timestamp = start_timestamp + (self.count - 1) * 60000

        symbol_splited = symbol.split('-')


        baseId = self.find_symbol_id(symbol_splited[0])
        quoteId = self.find_symbol_id(symbol_splited[1])

        payload = {
            'start': start_timestamp,
            'end': end_timestamp,
            'interval': 'm1',
            'exchange': 'binance',
            'baseId': baseId,
            'quoteId': quoteId,

        }

        response = requests.get(self.endpoint + 'candles', params=payload)
        self._handle_errors(response)

        data = response.json()['data']
        candles = []

        for d in data:
            candles.append({
                'id': jh.generate_unique_id(),
                'symbol': symbol,
                'exchange': self.name,
                'timestamp': int(d['period']),
                'open': float(d['open']),
                'close': float(d['close']),
                'high': float(d['high']),
                'low': float(d['low']),
                'volume': float(d['volume'])
            })

        return candles

    def find_symbol_id(self, symbol):

        payload = {
            'search': symbol,
        }

        response = requests.get(self.endpoint + 'assets', params=payload)
        self._handle_errors(response)
        data = response.json()['data']

        return data[0]['id']

    @staticmethod
    def _handle_errors(response):

        first_digit_code = int(str(response.status_code)[0])

        # Exchange In Maintenance
        if first_digit_code == 5:
            raise exceptions.ExchangeInMaintenance('Server ERROR. Please try again later')

        # unsupported user params
        if first_digit_code == 4:
            raise ValueError(response.json()['error'])

        if response.status_code != 200:
            raise Exception(response.content)
