import requests
import jesse.helpers as jh
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from jesse.enums import exchanges
from .ftx_utils import timeframe_to_interval


class FTXMain(CandleExchange):
    def __init__(
            self,
            name: str,
            rest_endpoint: str,
            backup_exchange_class,
    ) -> None:
        super().__init__(
            name=name,
            count=1440,
            rate_limit_per_second=6,
            backup_exchange_class=backup_exchange_class
        )

        self.endpoint = rest_endpoint

    def _formatted_symbol(self, symbol: str) -> str:
        if self.name in [exchanges.FTX_SPOT, exchanges.FTX_US_SPOT]:
            return symbol.replace('-', '/')
        elif self.name == exchanges.FTX_PERPETUAL_FUTURES:
            return symbol.replace('USD', 'PERP')
        else:
            raise NotImplemented(f'Unknown exchange {self.name}')

    def get_starting_time(self, symbol: str) -> int:
        end_timestamp = jh.now()
        start_timestamp = end_timestamp - (86400_000 * 365 * 8)

        payload = {
            'resolution': 86400,
            'start_time': start_timestamp / 1000,
            'end_time': end_timestamp / 1000,
        }

        response = requests.get(
            f'{self.endpoint}/api/markets/{self._formatted_symbol(symbol)}/candles',
            params=payload
        )

        self.validate_response(response)

        data = response.json()['result']

        # since the first timestamp doesn't include all the 1m
        # candles, let's start since the second day then
        first_timestamp = int(data[0]['time'])
        # second_timestamp:
        return first_timestamp + 60_000 * 1440

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str = '1m') -> list:
        end_timestamp = start_timestamp + (self.count - 1) * 60000 * jh.timeframe_to_one_minutes(timeframe)
        if end_timestamp > jh.now():
            end_timestamp = jh.now()
        interval = timeframe_to_interval(timeframe)

        payload = {
            'resolution': interval,
            'start_time': start_timestamp / 1000,
            'end_time': end_timestamp / 1000,
        }

        response = requests.get(
            f'{self.endpoint}/api/markets/{self._formatted_symbol(symbol)}/candles',
            params=payload
        )

        self.validate_response(response)

        data = response.json()['result']
        return [{
            'id': jh.generate_unique_id(),
            'exchange': self.name,
            'symbol': symbol,
            'timeframe': timeframe,
            'timestamp': int(d['time']),
            'open': float(d['open']),
            'close': float(d['close']),
            'high': float(d['high']),
            'low': float(d['low']),
            'volume': float(d['volume'])
        } for d in data]
