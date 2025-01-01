import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import jesse.helpers as jh
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from typing import Union
from jesse import exceptions
from .bybit_utils import timeframe_to_interval


class BybitMain(CandleExchange):
    def __init__(self, name: str, rest_endpoint: str, category: str) -> None:
        from jesse.modes.import_candles_mode.drivers.Binance.BinanceSpot import BinanceSpot

        super().__init__(name=name, count=200, rate_limit_per_second=10, backup_exchange_class=BinanceSpot)
        self.name = name
        self.endpoint = rest_endpoint
        self.category = category

        # Setup session with retry strategy
        self.session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[408, 429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST"]
        )
        self.session.mount('https://', HTTPAdapter(max_retries=retries, pool_maxsize=100))

    def get_starting_time(self, symbol: str) -> int:
        dashless_symbol = jh.dashless_symbol(symbol)
        payload = {
            'category': self.category,
            'symbol': dashless_symbol,
            'interval': 'W',
            'limit': 200,
            'start': 1514811660000
        }

        response = self.session.get(self.endpoint + '/v5/market/kline', params=payload, timeout=10)
        self.validate_response(response)
        data = response.json()['result']['list']
        # Reverse the data list
        data = data[::-1]
        return int(data[1][0])

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str = '1m') -> Union[list, None]:
        dashless_symbol = jh.dashless_symbol(symbol)
        interval = timeframe_to_interval(timeframe)
        payload = {
            'category': self.category,
            'symbol': dashless_symbol,
            'interval': interval,
            'start': int(start_timestamp),
            'limit': self.count
        }

        response = self.session.get(self.endpoint + '/v5/market/kline', params=payload, timeout=10)

        if response.json()['retMsg'] != 'OK':
            raise exceptions.SymbolNotFound(response.json()['retMsg'])
        data = response.json()['result']['list']
        # Reverse the data list
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
        response = self.session.get(self.endpoint + '/v5/market/instruments-info?limit=1000&category=' + self.category, timeout=10)
        self.validate_response(response)
        data = response.json()['result']['list']
        return [jh.dashy_symbol(d['symbol']) for d in data]
