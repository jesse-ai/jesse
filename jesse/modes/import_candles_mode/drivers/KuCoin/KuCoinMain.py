import requests
import jesse.helpers as jh
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from typing import Union
from .kucoin_utils import timeframe_to_interval
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class KuCoinMain(CandleExchange):
    def __init__(
            self,
            name: str,
            rest_endpoint: str,
            backup_exchange_class,
    ) -> None:
        super().__init__(
            name=name,
            count=1500,  # KuCoin allows up to 1500 candles per request
            rate_limit_per_second=10,  # KuCoin rate limit
            backup_exchange_class=backup_exchange_class
        )

        self.endpoint = rest_endpoint
        # Setup session with retry strategy
        self.session = requests.Session()
        retries = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
        )
        self.session.mount('http://', HTTPAdapter(max_retries=retries))
        self.session.mount('https://', HTTPAdapter(max_retries=retries))

    def _make_request(self, url: str, params: dict = None) -> requests.Response:
        max_retries = 3
        retry_delay = 5

        for attempt in range(max_retries):
            try:
                response = self.session.get(url, params=params, timeout=30)
                return response
            except (requests.exceptions.ConnectionError, OSError) as e:
                if "ERROR 451" in str(e):
                    raise Exception(
                        "Access to this exchange is restricted from your location (HTTP 451). "
                        "This is likely due to geographic restrictions imposed by the exchange. "
                        "You may need to use a VPN to change your IP address to a permitted location."
                    )
                if "Cannot allocate memory" in str(e):
                    # Force garbage collection and wait
                    import gc
                    gc.collect()
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                raise e

        raise Exception(f"Failed to make request after {max_retries} attempts")

    def get_starting_time(self, symbol: str) -> int:
        """
        Get the earliest available timestamp for a symbol
        """
        dashless_symbol = jh.dashless_symbol(symbol)

        payload = {
            'symbol': dashless_symbol,
            'type': '1day',
            'startAt': 0,
            'endAt': int(time.time() * 1000),
            'limit': 1
        }

        response = self._make_request(
            self.endpoint + '/api/v1/market/candles',
            params=payload
        )

        self.validate_response(response)

        data = response.json()
        
        if not data.get('data') or len(data['data']) == 0:
            raise ValueError(f"No data available for symbol {symbol}")

        # Get the first available timestamp
        first_timestamp = int(data['data'][0][0])
        # Add one day to ensure we have complete 1m data
        return first_timestamp + 60_000 * 1440

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str = '1m') -> Union[list, None]:
        end_timestamp = start_timestamp + (self.count - 1) * 60000 * jh.timeframe_to_one_minutes(timeframe)
        interval = timeframe_to_interval(timeframe)
        dashless_symbol = jh.dashless_symbol(symbol)

        payload = {
            'symbol': dashless_symbol,
            'type': interval,
            'startAt': int(start_timestamp),
            'endAt': int(end_timestamp),
            'limit': self.count,
        }

        response = self._make_request(
            self.endpoint + '/api/v1/market/candles',
            params=payload
        )

        self.validate_response(response)

        data = response.json()
        
        if not data.get('data'):
            return []

        # KuCoin returns data in reverse chronological order, so we reverse it
        candles_data = data['data'][::-1]
        
        return [{
            'id': jh.generate_unique_id(),
            'exchange': self.name,
            'symbol': symbol,
            'timeframe': timeframe,
            'timestamp': int(d[0]),
            'open': float(d[1]),
            'close': float(d[2]),
            'high': float(d[3]),
            'low': float(d[4]),
            'volume': float(d[5])
        } for d in candles_data]

    def get_available_symbols(self) -> list:
        response = self._make_request(self.endpoint + '/api/v1/symbols')

        self.validate_response(response)

        data = response.json()

        if not data.get('data'):
            return []

        # Filter only trading symbols
        trading_symbols = [symbol for symbol in data['data'] if symbol.get('enableTrading', False)]
        
        return [jh.dashy_symbol(s['symbol']) for s in trading_symbols]

    def __del__(self):
        """Cleanup method to ensure proper session closure"""
        if hasattr(self, 'session'):
            self.session.close()