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

    def get_starting_time(self, symbol: str) -> Union[int, None]:
        base_symbol = jh.get_base_asset(symbol)
        headers = {
            'Content-Type': 'application/json',
        }

        def first_candle(interval: str, start_time: int, end_time: int) -> Union[int, None]:
            payload = {
                'type': 'candleSnapshot',
                'req': {
                    'coin': base_symbol,
                    'interval': interval,
                    'startTime': start_time,
                    'endTime': end_time,
                }
            }
            response = requests.post(self.endpoint, json=payload, headers=headers)
            data = response.json()
            if not isinstance(data, list) or not data:
                return None
            return int(data[0]['t'])

        # Hyperliquid keeps only the latest 5,000 candles of each interval, and rejects a weekly
        # interval, so the daily snapshot (available since 2020) locates the listing day. Hourly
        # and minute snapshots then narrow it down when the listing is recent enough to still
        # be inside their retention; an older listing keeps the day start, which is never later
        # than the first real candle.
        now = int(jh.now_to_timestamp())
        first_timestamp = first_candle('1d', 0, now)
        if first_timestamp is None:
            return None
        for interval, window_ms in (('1h', 86_400_000), ('1m', 3_600_000)):
            refined = first_candle(interval, first_timestamp, first_timestamp + window_ms)
            if refined is None:
                break
            first_timestamp = refined
        return first_timestamp

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
