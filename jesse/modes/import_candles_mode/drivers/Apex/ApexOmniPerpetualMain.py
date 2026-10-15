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

    # Apex returns the newest candles of a window that exceeds its 200-row limit, so the first
    # candle is found by narrowing the window one interval at a time: month, week, day, hour,
    # minute. Each step is (interval, window length, look-back) in seconds; the look-back lets a
    # weekly bucket that starts in the previous month still be found.
    _FIRST_CANDLE_STEPS = (
        ('M', None, 0),
        ('W', 35 * 86400, 7 * 86400),
        ('D', 8 * 86400, 0),
        ('60', 86400, 0),
        ('1', 3600, 0),
    )

    def get_starting_time(self, symbol: str) -> Union[int, None]:
        dashless_symbol = jh.dashless_symbol(symbol)
        window_start = 1514811660
        window_end = int(jh.now_to_timestamp() / 1000)
        first_timestamp = None
        for interval, window_seconds, look_back in self._FIRST_CANDLE_STEPS:
            step_start = max(window_start - look_back, 0)
            payload = {
                'symbol': dashless_symbol,
                'interval': interval,
                'start': step_start,
                'end': window_end if window_seconds is None else step_start + window_seconds,
                'limit': 200,
            }
            response = requests.get(self.endpoint + '/klines', params=payload)
            self.validate_response(response)

            if 'data' not in response.json():
                raise exceptions.ExchangeInMaintenance(response.json()['msg'])
            # The full-history query validates the symbol. An empty narrower
            # window only ends refinement; it does not invalidate known history.
            elif response.json()['data'] == {} and first_timestamp is None:
                raise exceptions.InvalidSymbol('Exchange does not support the entered symbol. Please enter a valid symbol.')

            data = response.json()['data'].get(dashless_symbol) or []
            if not data:
                break
            first_timestamp = int(data[0]['t'])
            window_start = int(first_timestamp / 1000)
        return first_timestamp

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

        # Apex answers {"data": {}} when the window holds no closed bar yet (e.g. the live
        # tail request for the current minute), not only for unknown symbols. Keep symbol
        # validation in get_starting_time(), and allow this fetch window to have no candles.
        data = response.json()['data'].get(dashless_symbol) or []

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
