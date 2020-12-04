from polygon import RESTClient
from requests import HTTPError

import jesse.helpers as jh
from .interface import CandleExchange


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

        # Check if symbol exists. Raises HTTP 404 if it doesn't.
        try:
            exists = self.restclient.reference_ticker_details(symbol)
        except HTTPError:
            raise ValueError("Symbol ({}) probably doesn't exist.".format(symbol))

        payload = {
            'unadjusted': 'false',
            'sort': 'asc',
            'limit': self.count,
        }

        # Polygon takes string dates not timestamps
        start = jh.timestamp_to_date(start_timestamp)
        end = jh.timestamp_to_date(start_timestamp + (self.count) * 60000)
        response = self.restclient.stocks_equities_aggregates(symbol, 1, 'minute', start, end, **payload)

        data = response.results

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
