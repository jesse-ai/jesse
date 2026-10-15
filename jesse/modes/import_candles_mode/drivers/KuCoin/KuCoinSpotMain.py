import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import jesse.helpers as jh
from jesse import exceptions
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from .kucoin_utils import timeframe_to_spot_type


class KuCoinSpotMain(CandleExchange):
    """
    KuCoin SPOT candle importer.

    Endpoint: GET https://api.kucoin.com/api/v1/market/candles
      params: symbol=BTC-USDT, type=1min, startAt=<sec>, endAt=<sec>
      - startAt/endAt are in SECONDS (not ms).
      - max 1500 candles per request.
      - returned NEWEST-FIRST (descending) -> we reverse to oldest-first.
      - each candle is 7 STRINGS: [time(s), open, CLOSE, HIGH, LOW, volume, turnover]
        NOTE the field order: close comes BEFORE high/low (unlike most exchanges).
      - response envelope: {"code": "200000", "data": [...]}; code is a STRING.
        "200000" = ok, "429000" = rate limited.
    Public endpoint, no auth required.
    """

    def __init__(self, name: str, rest_endpoint: str) -> None:
        # KuCoin spot allows up to 1500 candles/req; we use 1000 as a safe page size.
        super().__init__(name=name, count=1000, rate_limit_per_second=5, backup_exchange_class=None)
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
            response = self.session.get(self.endpoint + '/api/v1/market/candles', params=params, timeout=15)
            self.validate_response(response)
            payload = response.json()
            code = payload.get('code')
            if code == '200000':  # KuCoin success code is the STRING "200000"
                return payload.get('data') or []
            if code == '429000':  # exchange-level rate limit -> exponential backoff and retry
                time.sleep(2 ** attempt)
                continue
            raise exceptions.SymbolNotFound(f"KuCoin spot error {code}: {payload.get('msg')}")
        raise ConnectionError('KuCoin spot: rate limited (429000) after retries')

    def get_starting_time(self, symbol: str) -> int:
        # Walk back from now in 1-week candles to find the oldest available candle.
        now_sec = int(time.time())
        params = {
            'symbol': symbol,  # KuCoin spot uses the dashed form as-is (BTC-USDT)
            'type': '1week',
            'startAt': 1262304000,  # 2010-01-01, well before any KuCoin listing
            'endAt': now_sec,
        }
        data = self._request(params)
        if not data:
            return None
        # data is newest-first; the last element is the oldest weekly candle (time in seconds)
        oldest = data[-1]
        return int(oldest[0]) * 1000  # seconds -> ms

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str = '1m') -> list:
        type_ = timeframe_to_spot_type(timeframe)
        interval_sec = jh.timeframe_to_one_minutes(timeframe) * 60
        start_sec = int(start_timestamp / 1000)
        # request exactly `count` candles forward from start: [start, start + count*interval)
        end_sec = start_sec + self.count * interval_sec
        params = {
            'symbol': symbol,  # dashed form (BTC-USDT) as the exchange expects
            'type': type_,
            'startAt': start_sec,  # SECONDS
            'endAt': end_sec,      # SECONDS
        }
        data = self._request(params)
        # KuCoin spot returns NEWEST-FIRST -> reverse to oldest-first for Jesse
        data = data[::-1]

        return [
            {
                'id': jh.generate_unique_id(),
                'exchange': self.name,
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': int(d[0]) * 1000,  # KuCoin returns OPEN time in SECONDS -> ms
                'open': float(d[1]),
                'close': float(d[2]),   # field[2] is CLOSE (KuCoin order: time,open,close,high,low,vol,turnover)
                'high': float(d[3]),    # field[3] is HIGH
                'low': float(d[4]),     # field[4] is LOW
                'volume': float(d[5]),
            } for d in data
        ]

    def get_available_symbols(self) -> list:
        response = self.session.get(self.endpoint + '/api/v2/symbols', timeout=15)
        self.validate_response(response)
        payload = response.json()
        if payload.get('code') != '200000':
            raise ConnectionError(f"KuCoin spot symbols error {payload.get('code')}: {payload.get('msg')}")
        return [d['symbol'] for d in payload['data'] if d.get('enableTrading')]
