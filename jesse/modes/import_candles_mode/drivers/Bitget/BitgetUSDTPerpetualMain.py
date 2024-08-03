from typing import Union
import requests
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from .bitget_utils import timeframe_to_interval
import jesse.helpers as jh
from jesse.enums import exchanges
from jesse import exceptions


class BitgetUSDTPerpetualMain(CandleExchange):
    def __init__(
            self,
            name: str,
            endpoint: str,
    ) -> None:
        super().__init__(
            name=name,
            count=100,
            rate_limit_per_second=18,
            backup_exchange_class=None
        )

        self.endpoint = endpoint

    def get_starting_time(self, symbol: str) -> int:
        payload = {
            'granularity': '1W',
            'symbol': self.jesse_symbol_to_bitget_usdt_contracts_symbol(symbol),
            'startTime': 1359291660000,
            'endTime': jh.now(force_fresh=True)
        }

        response = requests.get(self.endpoint + '/api/mix/v1/market/candles', params=payload)

        self.validate_bitget_response(response)

        data = response.json()

        # since the first timestamp doesn't include all the 1m
        # candles, let's start since the second day then
        return int(data[1][0])

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str = '1m') -> Union[list, None]:
        end_timestamp = start_timestamp + (self.count - 1) * 60000 * jh.timeframe_to_one_minutes(timeframe)

        payload = {
            'granularity': timeframe_to_interval(timeframe),
            'symbol': self.jesse_symbol_to_bitget_usdt_contracts_symbol(symbol),
            'startTime': int(start_timestamp),
            'endTime': int(end_timestamp)
        }

        response = requests.get(self.endpoint + '/api/mix/v1/market/candles', params=payload)

        self.validate_bitget_response(response)

        data = response.json()

        return [
            {
                'id': jh.generate_unique_id(),
                'exchange': self.name,
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': int(d[0]),
                'open': float(d[1]),
                'high': float(d[2]),
                'low': float(d[3]),
                'close': float(d[4]),
                'volume': float(d[5])
            } for d in data
        ]

    def jesse_symbol_to_bitget_usdt_contracts_symbol(self, symbol: str) -> str:
        if self.name == exchanges.BITGET_USDT_PERPETUAL:
            return f'{jh.dashless_symbol(symbol)}_UMCBL'
        elif self.name == exchanges.BITGET_USDT_PERPETUAL_TESTNET:
            return f'{jh.dashless_symbol(symbol)}_SUMCBL'
        else:
            raise NotImplemented('Invalid exchange: {}'.format(self.name))

    def validate_bitget_response(self, response):
        data = response.json()

        # 40019: wrong symbol
        if response.status_code == 400 and data['code'] == "40019":
            msg = 'Symbol not found. Check the symbol and try again.'
            if self.name == exchanges.BITGET_USDT_PERPETUAL_TESTNET:
                msg += f' Example of a valid symbol for "{self.name}": "SBTC-SUSDT"'
            raise exceptions.SymbolNotFound(msg)

        self.validate_response(response)

    def get_available_symbols(self) -> list:
        if self.name == exchanges.BITGET_USDT_PERPETUAL:
            product = 'umcbl'
        elif self.name == exchanges.BITGET_USDT_PERPETUAL_TESTNET:
            product = 'sumcbl'
        else:
            raise NotImplemented('Invalid exchange: {}'.format(self.name))

        response = requests.get(self.endpoint + '/api/mix/v1/market/contracts?productType=' + product)
        self.validate_bitget_response(response)
        data = response.json()['data']
        return [jh.dashy_symbol(s['symbolName']) for s in data]
