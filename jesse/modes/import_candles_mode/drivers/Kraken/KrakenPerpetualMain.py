import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import jesse.helpers as jh
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from typing import Union
from jesse import exceptions
from .kraken_utils import timeframe_to_futures_resolution


class KrakenPerpetualMain(CandleExchange):
    """
    Candle-import driver for Kraken Pro Futures (PF_ multi-collateral linear perpetuals).

    Uses the public Futures charts API:
        https://futures.kraken.com/api/charts/v1/trade/<symbol>/<resolution>?from=&to=
    `time` in the response is in MILLISECONDS and is the OPENING time of the candle.
    `from`/`to` query params are in SECONDS. The endpoint serves deep history (BTC perp
    1m data goes back well over a month, daily back years), but info.py keeps backtesting
    disabled by default until the per-pair 1m depth is fully validated. The live runtime
    still uses this driver to fetch warm-up candles.
    """

    def __init__(self, name: str, rest_endpoint: str) -> None:
        from jesse.modes.import_candles_mode.drivers.Binance.BinancePerpetualFutures import BinancePerpetualFutures

        super().__init__(name=name, count=5000, rate_limit_per_second=2,
                         backup_exchange_class=BinancePerpetualFutures)
        self.name = name
        self.endpoint = rest_endpoint

        self.session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[408, 429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST"]
        )
        self.session.mount('https://', HTTPAdapter(max_retries=retries, pool_maxsize=100))

        self._symbol_cache = {}

    def _jesse_to_kraken_symbol(self, symbol: str) -> str:
        # Jesse 'BTC-USD' -> Kraken Futures 'PF_XBTUSD'
        base = jh.get_base_asset(symbol)
        quote = jh.get_quote_asset(symbol)
        if base == 'BTC':
            base = 'XBT'
        return f'PF_{base}{quote}'

    def get_starting_time(self, symbol: str) -> int:
        k_symbol = self._jesse_to_kraken_symbol(symbol)
        # probe daily candles from the Kraken Futures launch era to find the oldest available
        url = f'{self.endpoint}/api/charts/v1/trade/{k_symbol}/1d'
        response = self.session.get(url, params={'from': 1577836800, 'to': jh.now() // 1000}, timeout=10)
        self.validate_response(response)
        candles = response.json().get('candles', [])
        if not candles:
            raise exceptions.SymbolNotFound(f'No candles available for {symbol} on {self.name}')
        # `time` is already ms and is the candle open time
        return int(candles[0]['time'])

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str = '1m') -> Union[list, None]:
        k_symbol = self._jesse_to_kraken_symbol(symbol)
        resolution = timeframe_to_futures_resolution(timeframe)
        one_min = jh.timeframe_to_one_minutes(timeframe)
        from_sec = int(start_timestamp / 1000)
        to_sec = from_sec + (self.count * one_min * 60)

        url = f'{self.endpoint}/api/charts/v1/trade/{k_symbol}/{resolution}'
        response = self.session.get(url, params={'from': from_sec, 'to': to_sec}, timeout=15)
        self.validate_response(response)
        candles = response.json().get('candles', [])

        # `time` is in MILLISECONDS and is the candle open time -> use as-is. Oldest-first.
        return [
            {
                'id': jh.generate_unique_id(),
                'exchange': self.name,
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': int(c['time']),
                'open': float(c['open']),
                'high': float(c['high']),
                'low': float(c['low']),
                'close': float(c['close']),
                'volume': float(c['volume']),
            } for c in candles
        ]

    def get_available_symbols(self) -> list:
        # use the Futures instruments endpoint to list tradeable PF_ perpetuals
        response = self.session.get(self.endpoint + '/derivatives/api/v3/instruments', timeout=10)
        self.validate_response(response)
        data = response.json()
        symbols = []
        for inst in data.get('instruments', []):
            sym = inst.get('symbol', '')
            if not sym.upper().startswith('PF_') or not inst.get('tradeable', False):
                continue
            # PF_XBTUSD -> BTC-USD
            core = sym[3:]  # XBTUSD
            if core.endswith('USD'):
                base = core[:-3]
                quote = 'USD'
            else:
                continue
            if base == 'XBT':
                base = 'BTC'
            symbols.append(f'{base}-{quote}')
        return symbols
