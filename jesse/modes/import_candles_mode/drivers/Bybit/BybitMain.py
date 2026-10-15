import requests
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import jesse.helpers as jh
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from typing import Union
from jesse import exceptions
from jesse.services.historical_data.errors import (
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderUnavailableError,
)
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

    def _get_kline_data(self, payload: dict) -> list:
        """Retry transient JSON failures that HTTP-level retries cannot see."""
        # Match the HTTP adapter's three-retry budget. Bybit's 10006 limit uses a
        # rolling one-second window; exponential waits avoid immediately hitting it again.
        for attempt in range(4):
            response = self.session.get(self.endpoint + '/v5/market/kline', params=payload, timeout=10)
            self.validate_response(response)
            data = response.json()
            code = data.get('retCode', 0)
            message = f"{payload['symbol']} on {self.name}: {data['retMsg']} (retCode={code})"
            # Bybit documents 10000 as a server timeout and 10016 as a server error.
            if code in (10006, 10000, 10016):
                error_type = ProviderRateLimitError if code == 10006 else ProviderUnavailableError
                if attempt == 3:
                    raise error_type(message)
                delay = float(2 ** attempt)
                reset = response.headers.get('X-Bapi-Limit-Reset-Timestamp') if code == 10006 else None
                if reset:
                    try:
                        delay = max(delay, float(reset) / 1000 - time.time())
                    except ValueError:
                        pass  # A malformed reset header must not disable the bounded fallback.
                # Do not block startup indefinitely on a bad or unusually distant reset timestamp.
                if delay > 30:
                    raise ProviderRateLimitError(
                        f"Bybit rate limit for {payload['symbol']} on {self.name}; retry after its limit resets."
                    )
                time.sleep(delay)
                continue
            if code != 0 or data['retMsg'] != 'OK':
                # 10001 also covers unrelated parameter errors; only symbol-specific
                # messages (or the explicit invalid-symbol code) mean a missing market.
                invalid_symbol_message = data['retMsg'].lower() in ('symbol invalid', 'invalid symbol')
                if (
                    code == 10029
                    or (code == 10001 and 'symbol' in data['retMsg'].lower())
                    # Retain explicit invalid-symbol errors even when the response omits its code.
                    or ('retCode' not in data and invalid_symbol_message)
                ):
                    raise exceptions.SymbolNotFound(message)
                raise ProviderRequestError(message)
            return data['result']['list']
        raise ProviderRateLimitError(f'Bybit rate limit on {self.name}')

    def get_starting_time(self, symbol: str) -> Union[int, None]:
        dashless_symbol = jh.dashless_symbol(symbol)
        # Bybit answers `start` in ascending order, so one 1m candle from 2018 is the exact
        # listing minute. The former weekly lookup skipped the whole listing week.
        payload = {
            'category': self.category,
            'symbol': dashless_symbol,
            'interval': '1',
            'limit': 1,
            'start': 1514811660000
        }

        data = self._get_kline_data(payload)
        if not data:
            return None
        return int(data[0][0])

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

        data = self._get_kline_data(payload)
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
