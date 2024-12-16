import requests
import time
from requests.exceptions import ConnectionError, RequestException

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
        self.base_delay = 3  # Base delay in seconds

    def _make_request(self, url: str, params: dict = None) -> requests.Response:
        for attempt in range(self.max_retries):
            try:
                response = requests.get(url, params=params)
                return response
            except (ConnectionError, RequestException) as e:
                if attempt == self.max_retries - 1:  # Last attempt
                    raise e
                
                # Exponential backoff with jitter
                delay = (self.base_delay * 2 ** attempt) + (jh.random_uniform(0, 1))
                time.sleep(delay)

    def get_starting_time(self, symbol: str) -> int:
        dashless_symbol = jh.dashless_symbol(symbol)

        # hard-code few common symbols
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

        # wrong symbol entered
        if not len(data):
            raise exceptions.SymbolNotFound(
                f"No candle exists for {symbol} in Bitfinex."
            )

        # since the first timestamp doesn't include all the 1m
        # candles, let's start since the second day then
        first_timestamp = int(data[0][0])
        return first_timestamp + 60_000 * 1440

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str) -> list:
        # since Bitfinex API skips candles with "volume=0", we have to send end_timestamp
        # instead of limit. Therefore, we use limit number to calculate the end_timestamp
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
            # if has : like CELO:USD, remove the : and make it CELOUSD
            if ':' in symbol:
                symbol = symbol.replace(':', '')
            arr.append(jh.dashy_symbol(symbol))

        return arr
