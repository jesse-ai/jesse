import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import jesse.helpers as jh
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from typing import Union
from jesse import exceptions
from .kraken_utils import timeframe_to_interval


class KrakenSpotMain(CandleExchange):
    """
    Candle-import driver for Kraken Pro Spot.

    NOTE: Kraken's public OHLC endpoint only serves the most recent ~720 candles per
    timeframe (a rolling window); older data cannot be retrieved regardless of `since`.
    That makes Kraken unsuitable for historical backtesting (info.py: backtesting=False),
    but this driver is still used by the live runtime to fetch warm-up candles, which only
    needs the most recent N candles.
    """

    # Kraken uses its own ticker for a few base assets (Bitcoin = XBT, Dogecoin = XDG) in the
    # AssetPairs 'wsname'. Normalize them to the market-standard names Jesse uses, both inbound
    # (wsname -> Jesse symbol) and outbound (Jesse symbol -> Kraken altname).
    _KRAKEN_BASE_ALIASES = {'XBT': 'BTC', 'XDG': 'DOGE'}            # Kraken -> Jesse
    _JESSE_TO_KRAKEN_BASE = {v: k for k, v in _KRAKEN_BASE_ALIASES.items()}  # Jesse -> Kraken

    def __init__(self, name: str, rest_endpoint: str) -> None:
        from jesse.modes.import_candles_mode.drivers.Binance.BinanceSpot import BinanceSpot

        super().__init__(name=name, count=720, rate_limit_per_second=1, backup_exchange_class=BinanceSpot)
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

        # cache of {jesse_dashy_symbol: kraken_altname} resolved lazily from AssetPairs
        self._altname_cache = {}
        self._wsname_to_altname = {}

    def _load_asset_pairs(self) -> None:
        if self._altname_cache:
            return
        response = self.session.get(self.endpoint + '/0/public/AssetPairs', timeout=10)
        self.validate_response(response)
        data = response.json()
        if data.get('error'):
            raise exceptions.SymbolNotFound(str(data['error']))
        for altname, info in data['result'].items():
            wsname = info.get('wsname')  # e.g. "XBT/USD" -> dashy "BTC-USD"; we normalize Kraken aliases
            if not wsname:
                continue
            base, quote = wsname.split('/')
            # Kraken uses its own tickers for some assets (BTC=XBT, DOGE=XDG); normalize to Jesse's
            # standard names so e.g. Dogecoin shows up as DOGE-USD, not XDG-USD (which the trade/WS
            # API would then reject because it only speaks the standard DOGE name).
            base = self._KRAKEN_BASE_ALIASES.get(base, base)
            quote = self._KRAKEN_BASE_ALIASES.get(quote, quote)
            jesse_symbol = f'{base}-{quote}'
            self._altname_cache[jesse_symbol] = info['altname']
            self._wsname_to_altname[jesse_symbol] = info['altname']

    def _jesse_to_kraken_pair(self, symbol: str) -> str:
        self._load_asset_pairs()
        if symbol in self._altname_cache:
            return self._altname_cache[symbol]
        # fallback: build an altname directly, mapping standard names back to Kraken's (BTC->XBT,
        # DOGE->XDG)
        base = jh.get_base_asset(symbol)
        quote = jh.get_quote_asset(symbol)
        base = self._JESSE_TO_KRAKEN_BASE.get(base, base)
        quote = self._JESSE_TO_KRAKEN_BASE.get(quote, quote)
        return base + quote

    def get_starting_time(self, symbol: str) -> int:
        # Kraken only serves a rolling window, so the oldest available candle is roughly
        # 720 * timeframe ago. We return the oldest 1m candle the OHLC endpoint will give us.
        pair = self._jesse_to_kraken_pair(symbol)
        payload = {'pair': pair, 'interval': 1}
        response = self.session.get(self.endpoint + '/0/public/OHLC', params=payload, timeout=10)
        self.validate_response(response)
        data = response.json()
        if data.get('error'):
            raise exceptions.SymbolNotFound(str(data['error']))
        # result is keyed by the pair's canonical name (not necessarily the altname we sent)
        result = data['result']
        candles = next(v for k, v in result.items() if k != 'last')
        # candle time is in SECONDS -> convert to ms
        return int(candles[0][0]) * 1000

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str = '1m') -> Union[list, None]:
        pair = self._jesse_to_kraken_pair(symbol)
        interval = timeframe_to_interval(timeframe)
        # `since` is in SECONDS; it returns candles AFTER that timestamp, oldest-first.
        payload = {
            'pair': pair,
            'interval': interval,
            'since': int(start_timestamp / 1000),
        }
        response = self.session.get(self.endpoint + '/0/public/OHLC', params=payload, timeout=10)
        self.validate_response(response)
        data = response.json()
        if data.get('error'):
            raise exceptions.SymbolNotFound(str(data['error']))

        result = data['result']
        candles = next(v for k, v in result.items() if k != 'last')

        # Kraken OHLC candle array: [time(sec), open, high, low, close, vwap, volume, count].
        # `time` is the OPENING time of the candle (start of the interval) -> use as-is, *1000.
        # Already oldest-first; do NOT reverse.
        return [
            {
                'id': jh.generate_unique_id(),
                'exchange': self.name,
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': int(c[0]) * 1000,
                'open': float(c[1]),
                'high': float(c[2]),
                'low': float(c[3]),
                'close': float(c[4]),
                'volume': float(c[6]),
            } for c in candles
        ]

    def get_available_symbols(self) -> list:
        self._load_asset_pairs()
        return list(self._altname_cache.keys())
