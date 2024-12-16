import requests
import jesse.helpers as jh
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from typing import Union
from jesse import exceptions
from .gate_utils import timeframe_to_interval
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class GateUSDTMain(CandleExchange):
    def __init__(self, name: str, rest_endpoint: str) -> None:
        super().__init__(name=name, count=200, rate_limit_per_second=10, backup_exchange_class=None)
        self.name = name
        self.limit = 2000
        self.endpoint = rest_endpoint
        
        # Setup session with retries
        self.session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504]
        )
        self.session.mount('https://', HTTPAdapter(max_retries=retries))

    def get_starting_time(self, symbol: str) -> int:
        symbol = jh.dashy_to_underline(symbol)
        payload = {
            'contract': symbol,
            'interval': '1w',
            'limit': 1000,
            'from': 1514811660
        }

        response = requests.get(f"{self.endpoint}/usdt/candlesticks", params=payload)
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
            'contract': symbol,
            'interval': interval,
            'from': int(start_timestamp / 1000),
            'to': int(end_timestamp / 1000),
        }

        max_retries = 3
        retry_delay = 5  # seconds

        for attempt in range(max_retries):
            try:
                response = self.session.get(
                    f"{self.endpoint}/usdt/candlesticks", 
                    params=payload, 
                    timeout=30
                )
                self.validate_response(response)
                break
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                if attempt == max_retries - 1:
                    raise
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff

        if response.json() == []:
            raise exceptions.InvalidSymbol('Exchange does not support the entered symbol. Please enter a valid symbol.')

        data = []
        for d in response.json():
            data.append({
                'id': jh.generate_unique_id(),
                'exchange': self.name,
                'symbol': jh.underline_to_dashy_symbol(symbol),
                'timeframe': timeframe,
                'timestamp': int(d['t']) * 1000,
                'open': float(d['o']),
                'close': float(d['c']),
                'high': float(d['h']),
                'low': float(d['l']),
                'volume': float(d['v'])
            })
        return data

    def get_available_symbols(self) -> list:
        pairs = []
        response = requests.get(f"{self.endpoint}/usdt/contracts")
        self.validate_response(response)
        data = response.json()
        for p in data:
            pairs.append(jh.underline_to_dashy_symbol(p['name']))

        return pairs
