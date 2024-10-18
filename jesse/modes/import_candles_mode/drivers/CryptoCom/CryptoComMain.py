from abc import abstractmethod
from typing import Union
import requests
import jesse.helpers as jh
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from .crypto_com_utils import timeframe_to_interval


class CryptoComMain(CandleExchange):
    def __init__(
            self,
            name: str,
            backup_exchange_class,
            instrument_type: str = ''
    ) -> None:
        super().__init__(
            name=name,
            count=300,
            rate_limit_per_second=100,
            backup_exchange_class=backup_exchange_class
        )

        self.endpoint = 'https://api.crypto.com'
        self.instrument_type = instrument_type

    def get_starting_time(self, symbol: str) -> int:
        mapped_symbol = self._get_mapped_symbol_name(symbol)

        payload = {
            'timeframe': '1d',
            'instrument_name': mapped_symbol,
            'count': 1500,
        }

        response = requests.get(self.endpoint + self._prefix_address + 'get-candlestick', params=payload)

        self.validate_response(response)

        data = response.json()['result']['data']

        # since the first timestamp doesn't include all the 1m
        # candles, let's start since the second day then
        first_timestamp = int(data[0]['t'])
        return first_timestamp + 60_000 * 1440

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str = '1m') -> Union[list, None]:
        end_timestamp = start_timestamp + (self.count - 1) * 60000 * jh.timeframe_to_one_minutes(timeframe)
        interval = timeframe_to_interval(timeframe)
        mapped_symbol = self._get_mapped_symbol_name(symbol)

        payload = {
            'timeframe': interval,
            'instrument_name': mapped_symbol,
            'start_ts': int(start_timestamp),
            'end_ts': int(end_timestamp),
            'count': self.count,
        }

        response = requests.get(self.endpoint + self._prefix_address + 'get-candlestick', params=payload)

        self.validate_response(response)

        data = response.json()['result']['data']
        return [{
            'id': jh.generate_unique_id(),
            'exchange': self.name,
            'symbol': symbol,
            'timeframe': timeframe,
            'timestamp': int(d['t']),
            'open': float(d['o']),
            'close': float(d['c']),
            'high': float(d['h']),
            'low': float(d['l']),
            'volume': float(d['v'])
        } for d in data]

    def get_available_symbols(self) -> list:
        response = requests.get(self.endpoint + self._prefix_address + 'get-instruments')

        self.validate_response(response)
        data = response.json()['result']['data']

        return [self._dashy_symbol(d['base_ccy'], d['quote_ccy']) for d in data if self._filter_by_inst_type(d)]

    @property
    def _prefix_address(self):
        return '/exchange/v1/public/'

    def _filter_by_inst_type(self, item):
        if not self.instrument_type:
            return True
        return item['inst_type'] == self.instrument_type

    def _dashy_symbol(self, base, quote):
        return f"{base}-{quote}"

    @abstractmethod
    def _get_mapped_symbol_name(self, dashy_symbol):
        pass
