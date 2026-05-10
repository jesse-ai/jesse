import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import jesse.helpers as jh
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from jesse.enums import exchanges
from .coinbase_utils import timeframe_to_interval


class CoinbaseSpot(CandleExchange):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.COINBASE_SPOT,
            count=300,
            rate_limit_per_second=1.5,
            backup_exchange_class=None
        )

        self.endpoint = 'https://api.coinbase.com/api/v3/brokerage/market/products'

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
        if symbol == 'BTC-USD':
            return 1438387200000
        elif symbol == 'ETH-USD':
            return 1464739200000
        elif symbol == 'LTC-USD':
            return 1477958400000

        return None

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str) -> list:
        end_timestamp = start_timestamp + (self.count - 1) * 60000 * jh.timeframe_to_one_minutes(timeframe)

        payload = {
            'granularity': timeframe_to_interval(timeframe),
            'start': int(start_timestamp / 1000),
            'end': int(end_timestamp / 1000),
        }

        response = self.session.get(
            f"{self.endpoint}/{symbol}/candles",
            params=payload,
            timeout=30
        )

        self.validate_response(response)

        data = response.json()['candles']
        data = data[::-1]
        return [
            {
                'id': jh.generate_unique_id(),
                'exchange': self.name,
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': int(d['start']) * 1000,
                'open': float(d['open']),
                'close': float(d['close']),
                'high': float(d['high']),
                'low': float(d['low']),
                'volume': float(d['volume'])
            } for d in data
        ]

    def get_available_symbols(self) -> list:
        response = self.session.get(self.endpoint, timeout=30)
        self.validate_response(response)
        data = response.json()['products']
        available_symbols = []
        for s in data:
            if len(s['alias_to']) == 0:
                available_symbols.append(s['product_id'])

        return available_symbols
