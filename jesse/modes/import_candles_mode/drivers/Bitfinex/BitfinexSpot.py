import requests
import time
from requests.exceptions import ConnectionError, RequestException
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import jesse.helpers as jh
from jesse import exceptions
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from jesse.enums import exchanges
from .bitfinex_utils import timeframe_to_interval


class BitfinexSpot(CandleExchange):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.BITFINEX_SPOT,
            count=1440,
            rate_limit_per_second=1,
            backup_exchange_class=None
        )

        self.endpoint = 'https://api-pub.bitfinex.com/v2/candles'
        self.max_retries = 5
        self.base_delay = 3

        self.session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
        )
        self.session.mount('https://', HTTPAdapter(max_retries=retries))

    def _make_request(self, url: str, params: dict = None) -> requests.Response:
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(url, params=params, timeout=30)
                return response
            except (ConnectionError, RequestException) as e:
                if attempt == self.max_retries - 1:
                    raise e
                
                delay = (self.base_delay * 2 ** attempt) + (jh.random_uniform(0, 1))
                time.sleep(delay)

    def __del__(self):
        try:
            self.session.close()
        except Exception:
            pass

    def get_starting_time(self, symbol: str) -> int:
        dashless_symbol = jh.dashless_symbol(symbol)

        if symbol == 'BTC-USD':
            return jh.date_to_timestamp('2015-08-01')
        elif symbol == 'ETH-USD':
            return jh.date_to_timestamp('2016-01-01')

        payload = {
            'sort': 1,
            'limit': 5000,
        }

        response = self._make_request(f"{self.endpoint}/trade:1D:t{dashless_symbol}/hist", params=payload)

        self.validate_response(response)

        data = response.json()

        if not len(data):
            raise exceptions.SymbolNotFound(
                f"No candle exists for {symbol} in Bitfinex."
            )

        first_timestamp = int(data[0][0])
        return first_timestamp + 60_000 * 1440

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str) -> list:
        end_timestamp = start_timestamp + (self.count - 1) * 60000 * jh.timeframe_to_one_minutes(timeframe)
        interval = timeframe_to_interval(timeframe)

        payload = {
            'start': start_timestamp,
            'end': end_timestamp,
            'limit': self.count,
            'sort': 1
        }

        dashless_symbol = jh.dashless_symbol(symbol)

        response = self._make_request(
            f"{self.endpoint}/trade:{interval}:t{dashless_symbol}/hist",
            params=payload
        )

        self.validate_response(response)

        data = response.json()
        return [{
            'id': jh.generate_unique_id(),
            'exchange': self.name,
            'symbol': symbol,
            'timeframe': timeframe,
            'timestamp': d[0],
            'open': d[1],
            'close': d[2],
            'high': d[3],
            'low': d[4],
            'volume': d[5]
        } for d in data]

    def get_available_symbols(self) -> list:
        response = self._make_request('https://api-pub.bitfinex.com/v2/conf/pub:list:pair:exchange')
        self.validate_response(response)
        data = response.json()[0]
        arr = []
        for s in data:
            symbol = s
            if ':' in symbol:
               arr.append(symbol.replace(':', '-'))
            else:
                arr.append(jh.dashy_symbol(symbol))

        return arr
