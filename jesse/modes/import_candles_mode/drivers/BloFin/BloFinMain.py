import requests
import jesse.helpers as jh
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from typing import Union
from jesse import exceptions
from .blofin_utils import timeframe_to_interval


class BloFinMain(CandleExchange):
    def __init__(self, name: str, rest_endpoint: str) -> None:
        from jesse.modes.import_candles_mode.drivers.Binance.BinanceSpot import BinanceSpot

        super().__init__(name=name, count=1440, rate_limit_per_second=10, backup_exchange_class=BinanceSpot)
        self.name = name
        self.endpoint = rest_endpoint

    def get_starting_time(self, symbol: str) -> int:
        payload = {
            'instId': symbol,
            'bar': '1W',
            'limit': 1440,
            'before': 1514811660
        }

        response = requests.get(self.endpoint + '/market/candles', params=payload)
        self.validate_response(response)

        if 'data' not in response.json():
            raise exceptions.ExchangeInMaintenance(response.json()['msg'])
        elif response.json()['data'] == {}:
            raise exceptions.InvalidSymbol('Exchange does not support the entered symbol. Please enter a valid symbol.')

        data = response.json()['data']
        # Reverse the data list
        data = data[::-1]
        return int(data[1][0])

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str = '1m') -> Union[list, None]:
        start = start_timestamp + self.count * jh.timeframe_to_one_minutes(timeframe) * 60000 + 60000
        payload = {
            'instId': symbol,
            'bar': timeframe,
            'after': int(start / 1000),
            'limit': self.count
        }

        response = requests.get(self.endpoint + '/market/candles', params=payload)
        # check data exist in response.json

        if 'data' not in response.json():
            raise exceptions.ExchangeInMaintenance(response.json()['msg'])
        elif response.json()['data'] == {}:
            raise exceptions.InvalidSymbol('Exchange does not support the entered symbol. Please enter a valid symbol.')

        data = response.json()['data']
        data = data[::-1]
        return [
            {
                'id': jh.generate_unique_id(),
                'exchange': self.name,
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': int(d[0]),
                'open': float(d[1]),
                'close': float(d[4]),
                'high': float(d[2]),
                'low': float(d[3]),
                'volume': float(d[5])
            } for d in data
        ]

    def get_available_symbols(self) -> list:
        response = requests.get(self.endpoint + '/market/tickers')
        self.validate_response(response)
        data = response.json()['data']
        pairs = []
        for p in data:
            symbol = p['instId']
            pairs.append(symbol)

        return list(sorted(pairs))
