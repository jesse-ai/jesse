from typing import Union

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import jesse.helpers as jh
from jesse import exceptions
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from .alpaca_utils import (
    DATA_ENDPOINT,
    FEED_STARTING_TIMESTAMPS,
    auth_headers,
    detect_feed,
    is_tradable_equity,
    jesse_symbol,
    alpaca_symbol,
    resolve_credentials,
    rfc3339_to_ms,
    ms_to_rfc3339,
    timeframe_to_alpaca,
)


class AlpacaStocksMain(CandleExchange):
    """
    Candle driver for US equities on Alpaca (market-data API).

    It is registered for all four Alpaca exchanges so the live runtime can fetch warm-up candles and
    refresh recent bars over REST; it is not offered as a backtest data source (info.py:
    backtesting=False) because the data plan of the account decides the feed (IEX-only on the free
    plan) and Massive already covers historical equity research.

    Bars are returned oldest-first with ``t`` = bar start in UTC, so timestamps map straight to
    Jesse's millisecond bar-start convention. Pre-market and after-hours bars are included, like the
    Massive imports, so backtests and live candles agree.
    Docs: https://docs.alpaca.markets/reference/stockbars
    """

    # Alpaca's page limit; the trading and data APIs share a 200 requests/minute budget on the
    # free plan, so pages are spaced out a little more than strictly needed.
    _PAGE_LIMIT = 10_000

    def __init__(self, name: str, trading_endpoint: str) -> None:
        super().__init__(name=name, count=self._PAGE_LIMIT, rate_limit_per_second=3, backup_exchange_class=None)
        self.name = name
        self.trading_endpoint = trading_endpoint
        self.session = requests.Session()
        retries = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[408, 429, 500, 502, 503, 504],
            allowed_methods=['GET'],
        )
        self.session.mount('https://', HTTPAdapter(max_retries=retries, pool_maxsize=20))
        self._headers = None
        self._feed = None
        self._symbols = None

    # --- helpers ---

    @property
    def headers(self) -> dict:
        if self._headers is None:
            api_key, api_secret = resolve_credentials()
            self._headers = auth_headers(api_key, api_secret)
        return self._headers

    @property
    def feed(self) -> str:
        if self._feed is None:
            self._feed = detect_feed(self.session, self.headers)
        return self._feed

    def _get(self, url: str, params: dict) -> dict:
        response = self.session.get(url, params=params, headers=self.headers, timeout=30)
        if response.status_code in (401, 403) and 'stocks' not in url:
            raise exceptions.InvalidExchangeApiKeys(f'Alpaca rejected the API key: {response.text[:200]}')
        self.validate_response(response)
        return response.json()

    # --- CandleExchange contract ---

    def get_starting_time(self, symbol: str) -> int:
        # The oldest bar depends on the feed (IEX history starts 2020-07-27, SIP 2016-01-01); ask
        # Alpaca for the first bar rather than trusting the constant, and fall back to it.
        payload = self._get(DATA_ENDPOINT + '/v2/stocks/bars', {
            'symbols': alpaca_symbol(symbol),
            'timeframe': '1Min',
            'start': ms_to_rfc3339(FEED_STARTING_TIMESTAMPS[self.feed] - 86_400_000),
            'limit': 1,
            'sort': 'asc',
            'feed': self.feed,
        })
        bars = payload.get('bars', {}).get(alpaca_symbol(symbol), [])
        if not bars:
            return FEED_STARTING_TIMESTAMPS[self.feed]
        return rfc3339_to_ms(bars[0]['t'])

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str = '1m') -> Union[list, None]:
        ticker = alpaca_symbol(symbol)
        params = {
            'symbols': ticker,
            'timeframe': timeframe_to_alpaca(timeframe),
            'start': ms_to_rfc3339(start_timestamp),
            'limit': self._PAGE_LIMIT,
            'sort': 'asc',
            'feed': self.feed,
            # Massive Stocks imports are split-adjusted; keep live warm-up on the same basis.
            'adjustment': 'split',
        }
        payload = self._get(DATA_ENDPOINT + '/v2/stocks/bars', params)
        # Alpaca omits the symbol key when the window holds no bar (a closed market, or an unknown
        # ticker); the live refresher polls the last few minutes all day, so empty is not an error.
        bars = payload.get('bars', {}).get(ticker) or []
        if not bars:
            known_tickers = self._known_tickers()
            if known_tickers is not None and ticker not in known_tickers:
                raise exceptions.SymbolNotFound(f'Alpaca does not list {symbol}. Check the symbol')

        return [
            {
                'id': jh.generate_unique_id(),
                'exchange': self.name,
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': rfc3339_to_ms(bar['t']),
                'open': float(bar['o']),
                'high': float(bar['h']),
                'low': float(bar['l']),
                'close': float(bar['c']),
                'volume': float(bar['v']),
            } for bar in bars
        ]

    def _known_tickers(self) -> set[str] | None:
        """Return the catalog when available; an outage cannot prove a ticker is invalid."""
        try:
            return {alpaca_symbol(s) for s in self.get_available_symbols()}
        except Exception:
            # the catalog is a convenience check; never turn a data hiccup into a symbol error
            return None

    def get_available_symbols(self) -> list:
        # The catalog is ~6 MB, so it is fetched once per process. Only listed, tradable US
        # equities are exposed; OTC names are left out on purpose.
        if self._symbols is None:
            assets = self._get(self.trading_endpoint + '/v2/assets', {'status': 'active', 'asset_class': 'us_equity'})
            self._symbols = sorted(jesse_symbol(a['symbol']) for a in assets if is_tradable_equity(a))
        return list(self._symbols)
