import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import jesse.helpers as jh
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from typing import Union
from .hyperliquid_utils import timeframe_to_interval


class HyperliquidPerpetualMain(CandleExchange):
    def __init__(self, name: str, rest_endpoint: str) -> None:
        from jesse.modes.import_candles_mode.drivers.Binance.BinanceSpot import BinanceSpot

        super().__init__(name=name, count=5000, rate_limit_per_second=10, backup_exchange_class=BinanceSpot)
        self.name = name
        self.endpoint = rest_endpoint

        self.session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
        )
        self.session.mount('https://', HTTPAdapter(max_retries=retries))

    def __del__(self):
        try:
            self.session.close()
        except Exception:
            pass

    def get_starting_time(self, symbol: str) -> int:
        base_symbol = jh.get_base_asset(symbol)
        payload = {
            'type': 'candleSnapshot',
            'req': {
                'coin': base_symbol,
                'interval': 'W',
                'startTime': 1514811660
            }
        }
        headers = {
            'Content-Type': 'application/json',
        }

        response = self.session.post(self.endpoint, json=payload, headers=headers, timeout=30)
        data = response.json()
        data = data[::-1]

        return int(data[1]['t'])

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str = '1m') -> Union[list, None]:
        base_symbol = jh.get_base_asset(symbol)
        interval = timeframe_to_interval(timeframe)
        payload = {
            'type': 'candleSnapshot',
            'req': {
                'coin': base_symbol,
                'interval': interval,
                'startTime': int(start_timestamp)
            }
        }

        headers = {
            'Content-Type': 'application/json',
        }
        response = self.session.post(self.endpoint, json=payload, headers=headers, timeout=30)
        self.validate_response(response)

        data = response.json()

        return [
            {
                'id': jh.generate_unique_id(),
                'exchange': self.name,
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': int(d['t']),
                'open': float(d['o']),
                'close': float(d['c']),
                'high': float(d['h']),
                'low': float(d['l']),
                'volume': float(d['v'])
            } for d in data
        ]

    def get_available_symbols(self) -> list:
        response = self.session.post(self.endpoint, json={'type': 'meta'}, timeout=30)
        self.validate_response(response)
        data = response.json()['universe']
        pairs = []
        for item in data:
            pairs.append(item['name'] + '-USD')

        return list(sorted(pairs))
