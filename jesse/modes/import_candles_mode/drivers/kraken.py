from .interface import CandleExchange
import requests
from jesse import exceptions
import jesse.helpers as jh


class Kraken(CandleExchange):
    """
    Kraken endpoint for candle data works with timestamps in seconds
    while jesse works with milliseconds
    """

    def __init__(self):
        super().__init__('Kraken', 720, 5)
        self.endpoint = 'https://api.kraken.com/0/public/OHLC'

    def init_backup_exchange(self):
        self.backup_exchange = None

    def get_starting_time(self, symbol):
        payload = {
            'interval': '1',
            'pair': symbol,
            'since': 000,
        }

        response = requests.get(self.endpoint, params=payload)
        self._handle_errors(response)

        data = response.json()
        first_timestamp = int(data["result"][self._topair(symbol)][0][0])
        return first_timestamp * 1000

    def fetch(self, symbol, start_timestamp):
        payload = {
            'interval': '1',
            'pair': symbol,
            'since': start_timestamp / 1000,
        }

        response = requests.get(self.endpoint, params=payload)
        self._handle_errors(response)
        data = response.json()["result"][self._topair(symbol)]
        candles = []
        for d in data:
            candles.append({
                'id': jh.generate_unique_id(),
                'symbol': symbol,
                'exchange': self.name,
                'timestamp': int(d[0]) * 1000,
                'open': float(d[1]),
                'close': float(d[4]),
                'high': float(d[2]),
                'low': float(d[3]),
                'volume': float(d[6])
            })

        return candles

    def _topair(self, symbol):
        return "X{}Z{}".format(symbol[:3], symbol[3:]).upper()

    @staticmethod
    def _handle_errors(response):
        # Exchange In Maintenance
        if response.status_code == 502:
            raise exceptions.ExchangeInMaintenance('ERROR: 502 Bad Gateway. Please try again later')
        # unsupported symbol
        if response.status_code == 404:
            raise ValueError(response.json()['message'])
        # generic error
        if response.status_code != 200:
            raise Exception(response.content)
        # error in body
        if response.json()["error"]:
            raise Exception(response.json()["error"])
