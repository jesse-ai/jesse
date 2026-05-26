import requests
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
        self.all_org_symbols = {}

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

        response = requests.post(self.endpoint, json=payload, headers=headers)
        data = response.json()
        # Reverse the data list
        data = data[::-1]

        return int(data[1]['t'])

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str = '1m') -> Union[list, None]:
        if self.all_org_symbols == {}:
            self.get_available_symbols()
            
        interval = timeframe_to_interval(timeframe)
        payload = {
            'type': 'candleSnapshot',
            'req': {
                'coin': self.all_org_symbols[symbol],
                'interval': interval,
                'startTime': int(start_timestamp)
            }
        }

        headers = {
            'Content-Type': 'application/json',
        }
        response = requests.post(self.endpoint, json=payload, headers=headers)
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
        response = requests.post(self.endpoint, json={'type': 'allPerpMetas'})
        self.validate_response(response)
        data = response.json()
        pairs = []
        
        for dex_info in data:
            universe = dex_info.get('universe', [])
            for item in universe:
                name = item['name']
                if ':' in name and name.split(':')[0] == 'xyz':
                    symbol = name.split(':')[1] + '-USD'
                elif ':' not in name:
                    symbol = name + '-USD'
                else:
                    continue
                    
                if symbol not in pairs:
                    pairs.append(symbol)
                    self.all_org_symbols[symbol] = name

        return list(sorted(pairs))
