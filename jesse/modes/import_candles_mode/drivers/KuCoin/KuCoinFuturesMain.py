import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import jesse.helpers as jh
from jesse import exceptions
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from .kucoin_utils import timeframe_to_futures_granularity, jesse_symbol_to_futures_contract


class KuCoinFuturesMain(CandleExchange):
    """
    KuCoin FUTURES candle importer.

    Endpoint: GET https://api-futures.kucoin.com/api/v1/kline/query
      params: symbol=XBTUSDTM, granularity=1, from=<ms>, to=<ms>
      - granularity is INTEGER MINUTES (1, 5, 60, 1440, ...).
      - from/to are in MILLISECONDS (unlike spot which is seconds).
      - max 500 candles per request.
      - returned OLDEST-FIRST (ascending) -> do NOT reverse.
      - each candle is 6 NUMBERS: [time(ms), open, HIGH, LOW, CLOSE, volume]
        NOTE: true OHLC order here (high/low before close) -- the OPPOSITE of spot.
      - response envelope: {"code": "200000", "data": [...]}; code is a STRING.
        "200000" = ok, "429000" = rate limited.
    Symbol mapping: Jesse BTC-USDT -> KuCoin contract XBTUSDTM (BTC -> XBT special-case).
    Public endpoint, no auth required.
    """

    def __init__(self, name: str, rest_endpoint: str) -> None:
        # KuCoin futures caps klines at 500/req.
        super().__init__(name=name, count=500, rate_limit_per_second=5, backup_exchange_class=None)
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

    def _request(self, params: dict) -> list:
        # retry on KuCoin's own 429000 rate-limit code (string), independent of HTTP 429
        for attempt in range(4):
            response = self.session.get(self.endpoint + '/api/v1/kline/query', params=params, timeout=15)
            self.validate_response(response)
            payload = response.json()
            code = payload.get('code')
            if code == '200000':  # KuCoin success code is the STRING "200000"
                return payload.get('data') or []
            if code == '429000':  # exchange-level rate limit -> exponential backoff and retry
                time.sleep(2 ** attempt)
                continue
            raise exceptions.SymbolNotFound(f"KuCoin futures error {code}: {payload.get('msg')}")
        raise ConnectionError('KuCoin futures: rate limited (429000) after retries')

    def get_starting_time(self, symbol: str) -> int:
        contract = jesse_symbol_to_futures_contract(symbol)
        # Ask for daily candles from 2018 forward; first element is the oldest available.
        params = {
            'symbol': contract,
            'granularity': 1440,  # 1 day
            'from': 1514764800000,   # 2018-01-01 in ms
            'to': int(time.time() * 1000),
        }
        data = self._request(params)
        if not data:
            return None
        # data is oldest-first; first element's time (ms) is the listing-era start
        return int(data[0][0])

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str = '1m') -> list:
        contract = jesse_symbol_to_futures_contract(symbol)
        granularity = timeframe_to_futures_granularity(timeframe)
        interval_ms = jh.timeframe_to_one_minutes(timeframe) * 60_000
        start_ms = int(start_timestamp)
        # request exactly `count` candles forward from start: [start, start + count*interval)
        end_ms = start_ms + self.count * interval_ms
        params = {
            'symbol': contract,
            'granularity': granularity,  # INTEGER minutes
            'from': start_ms,            # MILLISECONDS
            'to': end_ms,                # MILLISECONDS
        }
        data = self._request(params)
        # KuCoin futures returns OLDEST-FIRST already -> do NOT reverse.

        return [
            {
                'id': jh.generate_unique_id(),
                'exchange': self.name,
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': int(d[0]),  # KuCoin futures returns OPEN time in MILLISECONDS already
                'open': float(d[1]),
                'high': float(d[2]),    # field[2] is HIGH (futures order: time,open,high,low,close,vol)
                'low': float(d[3]),     # field[3] is LOW
                'close': float(d[4]),   # field[4] is CLOSE
                'volume': float(d[5]),
            } for d in data
        ]

    def get_available_symbols(self) -> list:
        response = self.session.get(self.endpoint + '/api/v1/contracts/active', timeout=15)
        self.validate_response(response)
        payload = response.json()
        if payload.get('code') != '200000':
            raise ConnectionError(f"KuCoin futures contracts error {payload.get('code')}: {payload.get('msg')}")
        symbols = []
        for c in payload['data']:
            # contract symbols look like XBTUSDTM / ETHUSDTM; strip the trailing 'M', map XBT->BTC
            sym = c['symbol']
            if not sym.endswith('USDTM'):
                continue
            base = sym[:-len('USDTM')]
            if base == 'XBT':
                base = 'BTC'
            symbols.append(f'{base}-USDT')
        return symbols
