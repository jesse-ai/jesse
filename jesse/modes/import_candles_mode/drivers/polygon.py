import requests

import jesse.helpers as jh
from jesse import exceptions
from .interface import CandleExchange
from jesse.config import config

from polygon import RESTClient

class Polygon(CandleExchange):

    def __init__(self):
        super().__init__('Polygon', 5000, 0.5, stock_mode=True)

        try:
            api_key = jh.get_config('env.exchanges.Polygon.api_key')
        except:
            raise ValueError("Polygon api_key missing in config.py")

        self.restclient = RESTClient(api_key)

    def init_backup_exchange(self):
        self.backup_exchange = None

    def get_starting_time(self, symbol):

        return None

    def fetch(self, symbol, start_timestamp):



        # Check if symbol exists. Returns status: "NOT_FOUND" in case it doesn't exist.
        response = self.restclient.reference_ticker_details(symbol)

        self._handle_errors(response)

        payload = {
            'unadjusted': 'false',
            'sort': 'asc',
            'limit': self.count,
        }

        # Polygon takes string dates not timestamps
        start_timestamp = jh.timestamp_to_date(start_timestamp)
        end_timestamp =  jh.timestamp_to_date(start_timestamp + (self.count) * 60000)
        response = self.restclient.stocks_equities_aggregates(symbol, 1, 'minute', start_timestamp, end_timestamp, payload)

        self._handle_errors(response)

        data = response.json()['results']

        candles = []

        for d in data:
            candles.append({
                'id': jh.generate_unique_id(),
                'symbol': symbol,
                'exchange': self.name,
                'timestamp': int(d['t']),
                'open': float(d['o']),
                'close': float(d['c']),
                'high': float(d['h']),
                'low': float(d['l']),
                'volume': int(d['v'])
            })

        return candles

    @staticmethod
    def _handle_errors(response):

        first_digit_code = int(str(response.status_code)[0])

        # Exchange In Maintenance
        if first_digit_code == 5:
            raise exceptions.ExchangeInMaintenance('Server ERROR. Please try again later')

        res_json = response.json()
        if res_json['status'] == "NOT_FOUND":
            raise ValueError("Symbol not found.")

        # unsupported user params
        if first_digit_code == 4:
            raise ValueError(res_json['error'])

        if response.status_code != 200:
            raise Exception(response.content)
