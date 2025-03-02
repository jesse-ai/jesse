import requests
import jesse.helpers as jh
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from typing import Union


class HyperliquidPerpetualMain(CandleExchange):
    def __init__(self, name: str, rest_endpoint: str) -> None:
        from jesse.modes.import_candles_mode.drivers.Binance.BinanceSpot import BinanceSpot

        super().__init__(name=name, count=5000, rate_limit_per_second=10, backup_exchange_class=BinanceSpot)
        self.name = name
        self.endpoint = rest_endpoint

    def get_starting_time(self, symbol: str) -> int:
        base_symbol = jh.get_base_asset(symbol)
        payload = {
            'type': 'candleSnapshot',
            'req': {
                'coin': base_symbol,
                'interval': '1w',
                'startTime': 1514811660
            }
        }
        headers = {
            'Content-Type': 'application/json',
        }

        response = requests.post(self.endpoint, json=payload, headers=headers)
        data = response.json()
        # Reverse the data list
        data = data[::-1]

        return int(data[1]['t'])

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str = '1m') -> Union[list, None]:
        base_symbol = jh.get_base_asset(symbol)

        payload = {
            'type': 'candleSnapshot',
            'req': {
                'coin': base_symbol,
                'interval': timeframe,
                'startTime': int(start_timestamp)
            }
        }

        headers = {
            'Content-Type': 'application/json',
        }
        response = requests.post(self.endpoint, json=payload, headers=headers)
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
        response = requests.post(self.endpoint, json={'type': 'meta'})
        self.validate_response(response)
        data = response.json()['universe']
        pairs = []
        for item in data:
            pairs.append(item['name'] + '-USD')

        return list(sorted(pairs))
