import requests
import jesse.helpers as jh
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from typing import Union
from jesse import exceptions
from .gate_utils import timeframe_to_interval


class GateSpotMain(CandleExchange):
    def __init__(self, name: str, rest_endpoint: str) -> None:
        super().__init__(name=name, count=200, rate_limit_per_second=10, backup_exchange_class=None)
        self.name = name
        self.limit = 1000
        self.endpoint = rest_endpoint

    def get_starting_time(self, symbol: str) -> int:
        symbol = jh.dashy_to_underline(symbol)
        payload = {
            'contract': symbol,
            'interval': '1w',
            'limit': 1000,
            'from': 1514811660
        }

        response = requests.get(f"{self.endpoint}/candlesticks", params=payload)
        self.validate_response(response)

        if response.json() == []:
            raise exceptions.InvalidSymbol('Exchange does not support the entered symbol. Please enter a valid symbol.')

        data = response.json()
        # Reverse the data list

        return int(data[0]['t'])

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str = '1m') -> Union[list, None]:
        symbol = jh.dashy_to_underline(symbol)
        end_timestamp = start_timestamp + (self.limit - 1) * 60000 * jh.timeframe_to_one_minutes(timeframe)
        interval = timeframe_to_interval(timeframe)

        payload = {
            'currency_pair': symbol,
            'interval': interval,
            'from': int(start_timestamp / 1000),
            'to': int(end_timestamp / 1000),
        }

        response = requests.get(f"{self.endpoint}/candlesticks", params=payload)
        self.validate_response(response)

        if response.json() == []:
            raise exceptions.InvalidSymbol('Exchange does not support the entered symbol. Please enter a valid symbol.')

        data = []
        for d in response.json():
            data.append({
                'id': jh.generate_unique_id(),
                'exchange': self.name,
                'symbol': jh.underline_to_dashy_symbol(symbol),
                'timeframe': timeframe,
                'timestamp': int(d[0]) * 1000,
                'open': float(d[5]),
                'close': float(d[2]),
                'high': float(d[3]),
                'low': float(d[4]),
                'volume': float(d[1])
            })
        return data

    def get_available_symbols(self) -> list:
        pairs = []
        response = requests.get(f"{self.endpoint}/currency_pairs")
        self.validate_response(response)
        data = response.json()

        for p in data:
            pairs.append(jh.underline_to_dashy_symbol(p['id']))

        return pairs
