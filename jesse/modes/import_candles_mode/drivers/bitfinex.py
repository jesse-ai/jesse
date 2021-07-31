import requests

import jesse.helpers as jh
from jesse import exceptions
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange


class Bitfinex(CandleExchange):
    def __init__(self) -> None:
        # import here instead of the top of the file to prevent possible the circular imports issue
        from jesse.modes.import_candles_mode.drivers.coinbase import Coinbase

        super().__init__(
            name='Bitfinex',
            count=1440,
            rate_limit_per_second=1,
            backup_exchange_class=Coinbase
        )

        self.endpoint = 'https://api-pub.bitfinex.com/v2/candles'

    def get_starting_time(self, symbol: str):
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

        response = requests.get(f"{self.endpoint}/trade:1D:t{dashless_symbol}/hist", params=payload)

        if response.status_code != 200:
            raise Exception(response.content)

        data = response.json()

        # wrong symbol entered
        if not len(data):
            raise exceptions.SymbolNotFound(
                f"No candle exists for {symbol} in Bitfinex. You're probably misspelling the symbol name."
            )

        # since the first timestamp doesn't include all the 1m
        # candles, let's start since the second day then
        first_timestamp = int(data[0][0])
        return first_timestamp + 60_000 * 1440

    def fetch(self, symbol: str, start_timestamp):
        # since Bitfinex API skips candles with "volume=0", we have to send end_timestamp
        # instead of limit. Therefore, we use limit number to calculate the end_timestamp
        end_timestamp = start_timestamp + (self.count - 1) * 60000

        payload = {
            'start': start_timestamp,
            'end': end_timestamp,
            'limit': self.count,
            'sort': 1
        }

        dashless_symbol = jh.dashless_symbol(symbol)

        response = requests.get(
            f"{self.endpoint}/trade:1m:t{dashless_symbol}/hist",
            params=payload
        )

        data = response.json()
        return [{
                'id': jh.generate_unique_id(),
                'symbol': symbol,
                'exchange': self.name,
                'timestamp': d[0],
                'open': d[1],
                'close': d[2],
                'high': d[3],
                'low': d[4],
                'volume': d[5]
            } for d in data]
