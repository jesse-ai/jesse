import requests
import jesse.helpers as jh
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from typing import Union
from jesse import exceptions
from .apex_omni_utils import timeframe_to_interval


class ApexOmniPerpetualMain(CandleExchange):
    def __init__(self, name: str, rest_endpoint: str) -> None:
        from jesse.modes.import_candles_mode.drivers.Binance.BinanceSpot import BinanceSpot

        super().__init__(name=name, count=200, rate_limit_per_second=10, backup_exchange_class=BinanceSpot)
        self.name = name
        self.endpoint = rest_endpoint

    def get_starting_time(self, symbol: str) -> int:
        dashless_symbol = jh.dashless_symbol(symbol)
        payload = {
            'symbol': dashless_symbol,
            'interval': 'W',
            'limit': 200,
            'start': 1514811660
        }

        response = requests.get(self.endpoint + '/klines', params=payload)
        self.validate_response(response)

        if 'data' not in response.json():
            raise exceptions.ExchangeInMaintenance(response.json()['msg'])
        elif response.json()['data'] == {}:
            raise exceptions.InvalidSymbol('Exchange does not support the entered symbol. Please enter a valid symbol.')

        data = response.json()['data'][dashless_symbol]
        # Reverse the data list
        data = data[::-1]

        return int(data[1]['t'])

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str = '1m') -> Union[list, None]:
        dashless_symbol = jh.dashless_symbol(symbol)
        interval = timeframe_to_interval(timeframe)

        payload = {
            'symbol': dashless_symbol,
            'interval': interval,
            'start': int(start_timestamp / 1000),
            'limit': self.count
        }

        response = requests.get(self.endpoint + '/klines', params=payload)
        # check data exist in response.json

        if 'data' not in response.json():
            raise exceptions.ExchangeInMaintenance(response.json()['msg'])
        elif response.json()['data'] == {}:
            raise exceptions.InvalidSymbol('Exchange does not support the entered symbol. Please enter a valid symbol.')

        data = response.json()['data'][dashless_symbol]

        return [
            {
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
            } for d in data
        ]

    def get_available_symbols(self) -> list:
        response = requests.get(self.endpoint + '/symbols')
        self.validate_response(response)
        data = response.json()['data']

        # Omni markets settle in USDT. The older response shape stores all
        # perpetual contracts together, so filter that list by settlement asset.
        if 'usdtConfig' not in data:
            symbols = []
            contracts = data['contractConfig']['perpetualContract']
            for p in contracts:
                symbol = p['symbol']
                if symbol.endswith('-USDT'):
                    symbols.append(symbol)
            return list(sorted(symbols))

        # The current response shape separates USDT and USDC contracts. Only
        # usdtConfig belongs to Apex Omni; usdcConfig was used by Apex Pro.
        pairs = []
        if 'perpetualContract' in data['usdtConfig']:
            contracts = data['usdtConfig']['perpetualContract']
            for p in contracts:
                symbol = p['symbol']
                if symbol.endswith('-USDT'):
                    pairs.append(symbol)

        return list(sorted(pairs))
