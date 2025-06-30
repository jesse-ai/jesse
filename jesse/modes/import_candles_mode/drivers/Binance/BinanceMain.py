import requests
import jesse.helpers as jh
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from typing import Union
from .binance_utils import timeframe_to_interval
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class BinanceMain(CandleExchange):
    def __init__(
            self,
            name: str,
            rest_endpoint: str,
            backup_exchange_class,
    ) -> None:
        super().__init__(
            name=name,
            count=1000,
            rate_limit_per_second=2,
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
        dashless_symbol = jh.dashless_symbol(symbol)

        payload = {
            'interval': '1d',
            'symbol': dashless_symbol,
            'limit': 1500,
        }

        response = self._make_request(
            self.endpoint + self._prefix_address + 'klines',
            params=payload
        )

        self.validate_response(response)

        data = response.json()

        # since the first timestamp doesn't include all the 1m
        # candles, let's start since the second day then
        first_timestamp = int(data[0][0])
        return first_timestamp + 60_000 * 1440

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str = '1m') -> Union[list, None]:
        end_timestamp = start_timestamp + (self.count - 1) * 60000 * jh.timeframe_to_one_minutes(timeframe)
        interval = timeframe_to_interval(timeframe)
        dashless_symbol = jh.dashless_symbol(symbol)

        payload = {
            'interval': interval,
            'symbol': dashless_symbol,
            'startTime': int(start_timestamp),
            'endTime': int(end_timestamp),
            'limit': self.count,
        }

        response = self._make_request(
            self.endpoint + self._prefix_address + 'klines',
            params=payload
        )

        self.validate_response(response)

        data = response.json()
        return [{
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
        } for d in data]

    def get_available_symbols(self) -> list:
        response = self._make_request(self.endpoint + self._prefix_address + 'exchangeInfo')

        self.validate_response(response)

        data = response.json()

        return [jh.dashy_symbol(d['symbol']) for d in data['symbols']]

    @property
    def _prefix_address(self):
        if self.name.startswith('Binance Perpetual Futures'):
            return '/v1/'
        return '/v3/'

    def __del__(self):
        """Cleanup method to ensure proper session closure"""
        if hasattr(self, 'session'):
            self.session.close()
