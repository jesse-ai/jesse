"""
FMP provider behavior against a fake HTTP session.

Every payload here is fabricated to mirror the shapes FMP's stable API returns (naive local
bar times, newest first, three-date windows); no real market data or keys are used.
"""

from datetime import datetime, timezone

import pytest

from jesse.services.historical_data import (
    FMPCommoditiesProvider,
    FMPCurrenciesProvider,
    FMPIndicesProvider,
    FMPStocksProvider,
    HistoricalCandleRange,
    HistoricalCandleRequest,
    SymbolCatalogEntry,
)
from jesse.services.historical_data.contracts import AdjustmentMode
from jesse.services.historical_data.errors import (
    HistoricalDataRequestError,
    ProviderAuthenticationError,
    ProviderEntitlementError,
    ProviderQuotaError,
    ProviderRateLimitError,
    ProviderSchemaError,
    ProviderSymbolNotFoundError,
    ProviderUnavailableError,
)
from jesse.services.historical_data.fmp import (
    FMP_AVAILABLE_EXCHANGES_URL,
    FMP_COMMODITIES_LIST_URL,
    FMP_COMPANY_SYMBOLS_URL,
    FMP_CRYPTO_LIST_URL,
    FMP_ETF_LIST_URL,
    FMP_FOREX_LIST_URL,
    FMP_FOUR_HOUR_URL,
    FMP_INDEX_LIST_URL,
    FMP_MARKET_HOURS_URL,
    FMP_ONE_MINUTE_URL,
    FMP_PROFILE_URL,
)


FAKE_KEY = 'fabricated-fmp-key'
MARKET_HOURS = [
    {'exchange': 'NASDAQ', 'timezone': 'America/New_York'},
    {'exchange': 'NYSE', 'timezone': 'America/New_York'},
    {'exchange': 'LSE', 'timezone': 'Europe/London'},
    {'exchange': 'SAU', 'timezone': 'Asia/Riyadh'},
    {'exchange': 'FGI', 'timezone': 'Europe/London'},
    {'exchange': 'BAD', 'timezone': 'Not/AZone'},
]


class _FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self._payload

    def close(self):
        pass


class _FakeFMPSession:
    """
    Answer FMP requests from handlers keyed by URL; each handler receives the query params.

    A handler returns a payload, or a `_FakeResponse` for non-200 answers.
    """

    def __init__(self, handlers):
        self.handlers = handlers
        self.requests = []

    def get(self, url, headers=None, params=None, timeout=None, allow_redirects=None):
        assert headers == {'apikey': FAKE_KEY}, 'the key must travel in the apikey header only'
        assert params is None or 'apikey' not in params
        assert timeout and allow_redirects is False
        self.requests.append((url, dict(params or {})))
        handler = self.handlers.get(url)
        if handler is None:
            raise AssertionError(f'Unexpected FMP request {url!r} {params!r}')
        result = handler(params or {})
        return result if isinstance(result, _FakeResponse) else _FakeResponse(result)


def _provider(cls, handlers, sleeps=None):
    session = _FakeFMPSession(handlers)
    provider = cls(
        credential_loader=lambda: FAKE_KEY,
        session=session,
        sleep=(sleeps.append if sleeps is not None else lambda _: None),
    )
    return provider, session


def _ms(value: str) -> int:
    return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp() * 1000)


def _request(symbol, start, end, adjustment=AdjustmentMode.NONE):
    return HistoricalCandleRequest(symbol, '1m', HistoricalCandleRange(_ms(start), _ms(end)), adjustment)


def _pair(resolved):
    return resolved.provider_symbol, resolved.timezone


def _bar(local_time, price=10.0, volume=100):
    return {'date': local_time, 'open': price, 'high': price + 1, 'low': price - 1, 'close': price, 'volume': volume}


def _profile(symbol, currency='USD', exchange='NASDAQ'):
    return lambda params: [{'symbol': symbol, 'currency': currency, 'exchange': exchange}] if params['symbol'] == symbol else []


def _profiles(*rows):
    by_symbol = {row['symbol']: row for row in rows}
    return lambda params: [by_symbol[params['symbol']]] if params['symbol'] in by_symbol else []


def _bars_by_window(bars_by_date):
    """Serve the bars of every local date inside the requested from/to window, newest first."""
    def handler(params):
        rows = [
            bar
            for day, bars in bars_by_date.items()
            if params['from'] <= day <= params['to']
            for bar in bars
        ]
        return sorted(rows, key=lambda row: row['date'], reverse=True)
    return handler


# ---------------------------------------------------------------------- candles


def test_stock_pages_split_into_three_date_windows_and_convert_new_york_time_to_utc():
    bars = {
        '2026-07-06': [_bar('2026-07-06 09:30:00', 1), _bar('2026-07-06 04:00:00', 2)],
        '2026-07-08': [_bar('2026-07-08 19:59:00', 3)],
        '2026-07-10': [_bar('2026-07-10 15:59:00', 4)],
    }
    provider, session = _provider(FMPStocksProvider, {
        FMP_PROFILE_URL: _profile('AAPL'),
        FMP_MARKET_HOURS_URL: lambda _: MARKET_HOURS,
        FMP_ONE_MINUTE_URL: _bars_by_window(bars),
    })

    batch = provider.fetch_candles(
        _request('AAPL-USD', '2026-07-06 04:00', '2026-07-11 00:00', AdjustmentMode.SPLIT_ADJUSTED)
    )

    # Summer New York time is UTC-4; results come back oldest first.
    assert [(c.timestamp, c.close) for c in batch.candles] == [
        (_ms('2026-07-06 08:00'), 2.0),
        (_ms('2026-07-06 13:30'), 1.0),
        (_ms('2026-07-08 23:59'), 3.0),
        (_ms('2026-07-10 19:59'), 4.0),
    ]
    chart_requests = [params for url, params in session.requests if url == FMP_ONE_MINUTE_URL]
    assert [(p['from'], p['to']) for p in chart_requests] == [
        ('2026-07-06', '2026-07-08'),
        ('2026-07-09', '2026-07-10'),
    ]
    assert all(p['symbol'] == 'AAPL' and p['extended'] == 'true' for p in chart_requests)
    assert 'nonadjusted' not in chart_requests[0]


def test_candles_outside_the_half_open_utc_range_are_dropped():
    provider, _ = _provider(FMPCurrenciesProvider, {
        FMP_FOREX_LIST_URL: lambda _: [{'symbol': 'EURUSD', 'fromCurrency': 'EUR', 'toCurrency': 'USD'}],
        FMP_CRYPTO_LIST_URL: lambda _: [],
        FMP_ONE_MINUTE_URL: _bars_by_window({'2026-07-06': [
            _bar('2026-07-06 07:59:00', 1),
            _bar('2026-07-06 08:00:00', 2),
            _bar('2026-07-06 08:01:00', 3),
        ]}),
    })

    batch = provider.fetch_candles(_request('EUR-USD', '2026-07-06 11:59', '2026-07-06 12:01'))

    assert [(c.timestamp, c.close) for c in batch.candles] == [
        (_ms('2026-07-06 11:59'), 1.0),
        (_ms('2026-07-06 12:00'), 2.0),
    ]


def test_bars_on_dates_outside_the_window_are_a_provider_error():
    # FMP answers a date it cannot use with the latest bars; those must never be stored silently.
    provider, _ = _provider(FMPCurrenciesProvider, {
        FMP_FOREX_LIST_URL: lambda _: [{'symbol': 'EURUSD', 'fromCurrency': 'EUR', 'toCurrency': 'USD'}],
        FMP_CRYPTO_LIST_URL: lambda _: [],
        FMP_ONE_MINUTE_URL: lambda _: [_bar('2026-11-03 10:00:00')],
    })

    with pytest.raises(ProviderSchemaError, match='outside the requested dates'):
        provider.fetch_candles(_request('EUR-USD', '2026-07-06 00:00', '2026-07-07 00:00'))


def test_daylight_saving_skipped_hour_is_dropped_and_repeated_hour_is_its_first_occurrence():
    provider, _ = _provider(FMPCurrenciesProvider, {
        FMP_FOREX_LIST_URL: lambda _: [],
        FMP_CRYPTO_LIST_URL: lambda _: [{'symbol': 'BTCUSD', 'name': 'Bitcoin USD'}],
        FMP_ONE_MINUTE_URL: _bars_by_window({
            '2026-03-08': [_bar('2026-03-08 01:59:00', 1), _bar('2026-03-08 02:30:00', 2), _bar('2026-03-08 03:00:00', 3)],
            '2026-11-01': [_bar('2026-11-01 01:30:00', 4)],
        }),
    })

    spring = provider.fetch_candles(_request('BTC-USD', '2026-03-08 05:00', '2026-03-08 08:00'))
    fall = provider.fetch_candles(_request('BTC-USD', '2026-11-01 04:00', '2026-11-01 08:00'))

    # 02:30 does not exist on the spring-forward date; 01:59 EST and 03:00 EDT are one minute apart.
    assert [(c.timestamp, c.close) for c in spring.candles] == [
        (_ms('2026-03-08 06:59'), 1.0),
        (_ms('2026-03-08 07:00'), 3.0),
    ]
    # The repeated 01:30 on the fall-back date is the first, daylight-time occurrence.
    assert [(c.timestamp, c.close) for c in fall.candles] == [(_ms('2026-11-01 05:30'), 4.0)]


def test_conflicting_duplicate_bars_are_rejected_and_identical_ones_merged():
    def handler(params):
        return [_bar('2026-07-06 10:00:00', 1), _bar('2026-07-06 10:00:00', 1)]

    provider, _ = _provider(FMPCommoditiesProvider, {
        FMP_COMMODITIES_LIST_URL: lambda _: [{'symbol': 'GCUSD', 'name': 'Gold Futures', 'currency': 'USD'}],
        FMP_ONE_MINUTE_URL: handler,
    })
    assert len(provider.fetch_candles(_request('GC-USD', '2026-07-06 00:00', '2026-07-07 00:00')).candles) == 1

    provider, _ = _provider(FMPCommoditiesProvider, {
        FMP_COMMODITIES_LIST_URL: lambda _: [{'symbol': 'GCUSD', 'name': 'Gold Futures', 'currency': 'USD'}],
        FMP_ONE_MINUTE_URL: lambda _: [_bar('2026-07-06 10:00:00', 1), _bar('2026-07-06 10:00:00', 2)],
    })
    with pytest.raises(ProviderSchemaError, match='conflicting'):
        provider.fetch_candles(_request('GC-USD', '2026-07-06 00:00', '2026-07-07 00:00'))


@pytest.mark.parametrize('bad_bar', [
    {**_bar('2026-07-06 10:00:00'), 'high': 5},
    {**_bar('2026-07-06 10:00:00'), 'close': 'x'},
    {**_bar('2026-07-06 10:00:00'), 'close': True},
    {**_bar('2026-07-06 10:00:00'), 'volume': -1},
    {**_bar('2026-07-06 10:00:00'), 'date': '06/07/2026 10:00'},
])
def test_invalid_bars_are_schema_errors(bad_bar):
    provider, _ = _provider(FMPCommoditiesProvider, {
        FMP_COMMODITIES_LIST_URL: lambda _: [{'symbol': 'GCUSD', 'name': 'Gold Futures', 'currency': 'USD'}],
        FMP_ONE_MINUTE_URL: lambda _: [bad_bar],
    })

    with pytest.raises(ProviderSchemaError):
        provider.fetch_candles(_request('GC-USD', '2026-07-06 00:00', '2026-07-07 00:00'))


def test_open_or_close_outside_the_range_widens_the_range_to_include_them():
    # Shape seen in FMP's earliest bars of some listings: the open sits one tick above the high.
    provider, _ = _provider(FMPCommoditiesProvider, {
        FMP_COMMODITIES_LIST_URL: lambda _: [{'symbol': 'GCUSD', 'name': 'Gold Futures', 'currency': 'USD'}],
        FMP_ONE_MINUTE_URL: lambda _: [
            {'date': '2026-07-06 10:00:00', 'open': 33.15, 'high': 33.1, 'low': 33.1, 'close': 33.1, 'volume': 5},
            {'date': '2026-07-06 10:01:00', 'open': 33.1, 'high': 33.15, 'low': 33.15, 'close': 33.15, 'volume': 5},
        ],
    })

    candles = provider.fetch_candles(_request('GC-USD', '2026-07-06 00:00', '2026-07-07 00:00')).candles

    assert [(c.open, c.high, c.low, c.close) for c in candles] == [
        (33.15, 33.15, 33.1, 33.1),
        (33.1, 33.15, 33.1, 33.15),
    ]


def test_rows_stamped_mid_minute_are_skipped():
    # FMP's history holds stray zero-volume snapshots stamped at odd seconds; they are not bars.
    provider, _ = _provider(FMPCommoditiesProvider, {
        FMP_COMMODITIES_LIST_URL: lambda _: [{'symbol': 'GCUSD', 'name': 'Gold Futures', 'currency': 'USD'}],
        FMP_ONE_MINUTE_URL: lambda _: [_bar('2026-07-06 10:01:00', 2), {**_bar('2026-07-06 10:00:30', 9), 'volume': 0}],
    })

    candles = provider.fetch_candles(_request('GC-USD', '2026-07-06 00:00', '2026-07-07 00:00')).candles

    assert [(c.timestamp, c.close) for c in candles] == [(_ms('2026-07-06 14:01'), 2.0)]


def test_bars_without_volume_record_zero_volume():
    provider, _ = _provider(FMPIndicesProvider, {
        FMP_INDEX_LIST_URL: lambda _: [{'symbol': '^FTSE', 'name': 'FTSE 100', 'exchange': 'FGI', 'currency': 'GBP'}],
        FMP_MARKET_HOURS_URL: lambda _: MARKET_HOURS,
        FMP_ONE_MINUTE_URL: lambda _: [{'date': '2026-07-06 08:00:00', 'open': 1, 'high': 2, 'low': 1, 'close': 2}],
    })

    candles = provider.fetch_candles(_request('FTSE-GBP', '2026-07-06 00:00', '2026-07-07 00:00')).candles

    # London summer time is UTC+1.
    assert [(c.timestamp, c.volume) for c in candles] == [(_ms('2026-07-06 07:00'), 0.0)]


def test_stocks_require_split_adjusted_requests():
    provider, _ = _provider(FMPStocksProvider, {})

    with pytest.raises(HistoricalDataRequestError):
        provider.fetch_candles(_request('AAPL-USD', '2026-07-06 00:00', '2026-07-07 00:00', AdjustmentMode.NONE))


# ---------------------------------------------------------------------- earliest timestamp


def test_earliest_timestamp_scans_four_hour_windows_forward_and_starts_at_local_midnight():
    def four_hour(params):
        # History begins on 2003-09-10; earlier windows are empty.
        if params['to'] < '2003-09-10':
            return []
        return [{'date': '2003-09-11 09:30:00', 'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1},
                {'date': '2003-09-10 13:30:00', 'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1}]

    provider, session = _provider(FMPStocksProvider, {
        FMP_PROFILE_URL: _profile('AAPL'),
        FMP_MARKET_HOURS_URL: lambda _: MARKET_HOURS,
        FMP_FOUR_HOUR_URL: four_hour,
    })

    earliest = provider.find_earliest_available_timestamp(
        _request('AAPL-USD', '2003-01-01 00:00', '2026-11-05 00:00', AdjustmentMode.SPLIT_ADJUSTED)
    )

    # Midnight in New York (UTC-4 in September) keeps that day's pre-market minutes in the import.
    assert earliest == _ms('2003-09-10 04:00')
    windows = [(p['from'], p['to']) for url, p in session.requests if url == FMP_FOUR_HOUR_URL]
    assert windows[0] == ('2002-12-31', '2003-05-29')
    assert all(p['extended'] == 'true' for url, p in session.requests if url == FMP_FOUR_HOUR_URL)
    # Consecutive windows touch without overlapping.
    assert all(
        datetime.fromisoformat(next_from).date().toordinal() == datetime.fromisoformat(prev_to).date().toordinal() + 1
        for (_, prev_to), (next_from, _) in zip(windows, windows[1:])
    )


def test_earliest_timestamp_is_never_before_the_requested_start_and_none_without_data():
    provider, _ = _provider(FMPCurrenciesProvider, {
        FMP_FOREX_LIST_URL: lambda _: [{'symbol': 'EURUSD', 'fromCurrency': 'EUR', 'toCurrency': 'USD'}],
        FMP_CRYPTO_LIST_URL: lambda _: [],
        FMP_FOUR_HOUR_URL: lambda params: [_bar(f'{params["from"]} 20:00:00')],
    })
    request = _request('EUR-USD', '2026-07-06 12:00', '2026-07-08 00:00')
    assert provider.find_earliest_available_timestamp(request) == _ms('2026-07-06 12:00')

    provider, _ = _provider(FMPCurrenciesProvider, {
        FMP_FOREX_LIST_URL: lambda _: [{'symbol': 'EURUSD', 'fromCurrency': 'EUR', 'toCurrency': 'USD'}],
        FMP_CRYPTO_LIST_URL: lambda _: [],
        FMP_FOUR_HOUR_URL: lambda _: [],
    })
    assert provider.find_earliest_available_timestamp(request) is None


# ---------------------------------------------------------------------- symbol resolution


def test_stock_dots_resolve_to_fmp_class_dashes_and_exchange_timezones():
    provider, session = _provider(FMPStocksProvider, {
        FMP_PROFILE_URL: _profiles(
            {'symbol': 'BRK-B', 'currency': 'USD', 'exchange': 'NYSE'},
            {'symbol': 'VOD.L', 'currency': 'GBp', 'exchange': 'LSE'},
        ),
        FMP_MARKET_HOURS_URL: lambda _: MARKET_HOURS,
    })

    assert _pair(provider._resolve('BRK.B-USD', FAKE_KEY)) == ('BRK-B', 'America/New_York')
    # London prices are in pence, which Jesse spells GBX so they are never mistaken for pounds.
    assert _pair(provider._resolve('VOD.L-GBX', FAKE_KEY)) == ('VOD.L', 'Europe/London')
    profile_lookups = [p['symbol'] for url, p in session.requests if url == FMP_PROFILE_URL]
    assert profile_lookups == ['BRK.B', 'BRK-B', 'VOD.L', 'VOD-L']
    # The exchange table is loaded once per provider.
    assert sum(url == FMP_MARKET_HOURS_URL for url, _ in session.requests) == 1


def test_stock_with_wrong_currency_says_which_symbol_to_import():
    provider, _ = _provider(FMPStocksProvider, {
        FMP_PROFILE_URL: _profiles({'symbol': 'VOD.L', 'currency': 'GBp', 'exchange': 'LSE'}),
    })

    with pytest.raises(ProviderSymbolNotFoundError, match='import it as VOD.L-GBX'):
        provider._resolve('VOD.L-GBP', FAKE_KEY)


def test_unknown_ambiguous_and_timezone_less_stocks_fail_clearly():
    provider, _ = _provider(FMPStocksProvider, {FMP_PROFILE_URL: lambda _: []})
    with pytest.raises(ProviderSymbolNotFoundError, match='no stock or ETF'):
        provider._resolve('NOPE-USD', FAKE_KEY)

    provider, _ = _provider(FMPStocksProvider, {
        FMP_PROFILE_URL: _profiles(
            {'symbol': 'BT.A.L', 'currency': 'GBp', 'exchange': 'LSE'},
            {'symbol': 'BT-A.L', 'currency': 'GBp', 'exchange': 'LSE'},
        ),
    })
    with pytest.raises(ProviderSymbolNotFoundError, match='more than one FMP listing'):
        provider._resolve('BT.A.L-GBX', FAKE_KEY)

    provider, _ = _provider(FMPStocksProvider, {
        FMP_PROFILE_URL: _profiles({'symbol': 'ODD', 'currency': 'USD', 'exchange': 'MOON'}),
        FMP_MARKET_HOURS_URL: lambda _: MARKET_HOURS,
    })
    with pytest.raises(ProviderSchemaError, match='timezone'):
        provider._resolve('ODD-USD', FAKE_KEY)

    with pytest.raises(HistoricalDataRequestError, match='BASE-QUOTE'):
        provider._resolve('AAPL', FAKE_KEY)


def test_indices_resolve_through_the_index_list_including_fallback_exchanges():
    provider, _ = _provider(FMPIndicesProvider, {
        FMP_INDEX_LIST_URL: lambda _: [
            {'symbol': '^GSPC', 'name': 'S&P 500', 'exchange': 'SNP', 'currency': 'USD'},
            {'symbol': '^N225', 'name': 'Nikkei 225', 'exchange': 'OSA', 'currency': 'JPY'},
            {'symbol': 'DX-Y.NYB', 'name': 'US Dollar Index', 'exchange': 'NYSE', 'currency': 'USD'},
        ],
        FMP_MARKET_HOURS_URL: lambda _: MARKET_HOURS,
    })

    assert _pair(provider._resolve('GSPC-USD', FAKE_KEY)) == ('^GSPC', 'America/New_York')
    assert _pair(provider._resolve('N225-JPY', FAKE_KEY)) == ('^N225', 'Asia/Tokyo')
    assert _pair(provider._resolve('DX.Y.NYB-USD', FAKE_KEY)) == ('DX-Y.NYB', 'America/New_York')
    with pytest.raises(ProviderSymbolNotFoundError):
        provider._resolve('GSPC-EUR', FAKE_KEY)


# ---------------------------------------------------------------------- catalogs


def test_stock_catalog_lists_companies_with_their_currency_and_us_etfs():
    provider, _ = _provider(FMPStocksProvider, {
        FMP_COMPANY_SYMBOLS_URL: lambda _: [
            {'symbol': 'AAPL', 'companyName': 'Apple Inc.', 'tradingCurrency': 'USD'},
            {'symbol': 'VOD.L', 'companyName': 'Vodafone Group', 'tradingCurrency': 'GBp'},
            {'symbol': 'NPN.JO', 'companyName': 'Naspers', 'tradingCurrency': 'ZAc'},
            {'symbol': 'VOLV-B.ST', 'companyName': 'Volvo B', 'tradingCurrency': 'SEK'},
            {'symbol': '2222.SR', 'companyName': 'Saudi Aramco', 'tradingCurrency': 'SAR'},
            # Collide once FMP's class dash becomes a dot; neither can be imported unambiguously.
            {'symbol': 'BT-A.L', 'companyName': 'BT Group A', 'tradingCurrency': 'GBp'},
            {'symbol': 'BT.A.L', 'companyName': 'BT Group', 'tradingCurrency': 'GBp'},
            # Unknown minor units and unrepresentable tickers are left out.
            {'symbol': 'ODD.XX', 'companyName': 'Odd', 'tradingCurrency': 'XYz'},
            {'symbol': 'BAD_TICKER', 'companyName': 'Bad', 'tradingCurrency': 'USD'},
        ],
        FMP_ETF_LIST_URL: lambda _: [
            {'symbol': 'SPY', 'name': 'SPDR S&P 500 ETF Trust'},
            {'symbol': 'VUSA.L', 'name': 'Vanguard S&P 500 UCITS ETF'},
        ],
        FMP_AVAILABLE_EXCHANGES_URL: lambda _: [
            {'exchange': 'LSE', 'name': 'London Stock Exchange', 'symbolSuffix': '.L'},
            {'exchange': 'STO', 'name': 'Stockholm Stock Exchange', 'symbolSuffix': '.ST'},
            {'exchange': 'NASDAQ', 'name': 'NASDAQ', 'symbolSuffix': 'N/A'},
        ],
    })

    entries = provider.list_symbol_entries()

    assert entries == (
        SymbolCatalogEntry('2222.SR-SAR', name='Saudi Aramco', kind='Stock'),
        SymbolCatalogEntry('AAPL-USD', name='Apple Inc.', kind='Stock', venue='US'),
        SymbolCatalogEntry('NPN.JO-ZAC', name='Naspers', kind='Stock'),
        SymbolCatalogEntry('SPY-USD', name='SPDR S&P 500 ETF Trust', kind='ETF', venue='US'),
        SymbolCatalogEntry('VOD.L-GBX', name='Vodafone Group', kind='Stock', venue='London Stock Exchange'),
        SymbolCatalogEntry('VOLV.B.ST-SEK', name='Volvo B', kind='Stock', venue='Stockholm Stock Exchange'),
    )
    assert provider.search_symbols('volvo') == ('VOLV.B.ST-SEK',)
    assert provider.search_symbols('SPY') == ('SPY-USD',)
    # Names match too: 'sp' finds Naspers by name and SPY by ticker.
    assert provider.search_symbols('sp') == ('NPN.JO-ZAC', 'SPY-USD')


def test_currency_index_and_commodity_catalogs():
    currencies, _ = _provider(FMPCurrenciesProvider, {
        FMP_FOREX_LIST_URL: lambda _: [
            {'symbol': 'EURUSD', 'fromCurrency': 'EUR', 'toCurrency': 'USD', 'fromName': 'Euro', 'toName': 'US Dollar'},
            {'symbol': 'MISMATCH', 'fromCurrency': 'GBP', 'toCurrency': 'USD'},
        ],
        FMP_CRYPTO_LIST_URL: lambda _: [
            {'symbol': 'BTCUSD', 'name': 'Bitcoin USD'},
            {'symbol': 'USDE', 'name': 'No quote suffix'},
        ],
    })
    assert currencies.list_symbol_entries() == (
        SymbolCatalogEntry('BTC-USD', name='Bitcoin USD', kind='Crypto'),
        SymbolCatalogEntry('EUR-USD', name='Euro / US Dollar', kind='Forex'),
    )

    indices, _ = _provider(FMPIndicesProvider, {
        FMP_INDEX_LIST_URL: lambda _: [
            {'symbol': '^SP500-55', 'name': 'S&P 500 Utilities', 'exchange': 'SNP', 'currency': 'USD'},
            {'symbol': '^FTSE', 'name': 'FTSE 100', 'exchange': 'FGI', 'currency': 'GBP'},
            # An exchange without a known timezone cannot be converted to UTC, so it is left out.
            {'symbol': 'MSCIWORLD', 'name': 'MSCI World', 'exchange': 'MSC', 'currency': 'USD'},
        ],
        FMP_MARKET_HOURS_URL: lambda _: MARKET_HOURS,
    })
    assert indices.list_symbol_entries() == (
        SymbolCatalogEntry('FTSE-GBP', name='FTSE 100', kind='Index'),
        SymbolCatalogEntry('SP500.55-USD', name='S&P 500 Utilities', kind='Index'),
    )

    commodities, _ = _provider(FMPCommoditiesProvider, {
        FMP_COMMODITIES_LIST_URL: lambda _: [
            {'symbol': 'GCUSD', 'name': 'Gold Futures', 'currency': 'USD'},
            {'symbol': 'ZCUSX', 'name': 'Corn Futures', 'currency': 'USX'},
            {'symbol': 'ODDEUR', 'name': 'Mislabelled', 'currency': 'USD'},
        ],
    })
    assert commodities.list_symbol_entries() == (
        SymbolCatalogEntry('GC-USD', name='Gold Futures', kind='Future'),
        SymbolCatalogEntry('ZC-USX', name='Corn Futures', kind='Future'),
    )


def test_empty_catalog_is_a_provider_error():
    provider, _ = _provider(FMPCommoditiesProvider, {FMP_COMMODITIES_LIST_URL: lambda _: []})

    with pytest.raises(ProviderSchemaError, match='empty'):
        provider.list_symbol_entries()


# ---------------------------------------------------------------------- transport errors


def _commodity_handlers(chart):
    return {
        FMP_COMMODITIES_LIST_URL: lambda _: [{'symbol': 'GCUSD', 'name': 'Gold Futures', 'currency': 'USD'}],
        FMP_ONE_MINUTE_URL: chart,
    }


def test_rate_limits_wait_for_retry_after_then_succeed():
    answers = iter([
        _FakeResponse({'Error Message': 'Too many requests'}, 429, {'Retry-After': '7'}),
        [_bar('2026-07-06 10:00:00')],
    ])
    sleeps = []
    provider, _ = _provider(FMPCommoditiesProvider, _commodity_handlers(lambda _: next(answers)), sleeps)

    batch = provider.fetch_candles(_request('GC-USD', '2026-07-06 00:00', '2026-07-07 00:00'))

    assert len(batch.candles) == 1
    assert sleeps == [7.0]


def test_fmp_per_minute_limit_message_is_waited_out_not_treated_as_a_quota():
    # FMP's real per-minute limit answer: 429, this exact wording, and no Retry-After header.
    limit = {'Error Message': 'Limit Reach . Please upgrade your plan or visit our documentation for more details'}
    answers = iter([_FakeResponse(limit, 429), _FakeResponse(limit, 200), [_bar('2026-07-06 10:00:00')]])
    sleeps = []
    provider, _ = _provider(FMPCommoditiesProvider, _commodity_handlers(lambda _: next(answers)), sleeps)

    batch = provider.fetch_candles(_request('GC-USD', '2026-07-06 00:00', '2026-07-07 00:00'))

    assert len(batch.candles) == 1
    assert sleeps == [60.0, 60.0]


def test_rate_limit_without_retry_after_waits_one_minute_and_gives_up_after_four_attempts():
    sleeps = []
    provider, session = _provider(
        FMPCommoditiesProvider,
        _commodity_handlers(lambda _: _FakeResponse({}, 429)),
        sleeps,
    )

    with pytest.raises(ProviderRateLimitError):
        provider.fetch_candles(_request('GC-USD', '2026-07-06 00:00', '2026-07-07 00:00'))

    assert sleeps == [60.0, 60.0, 60.0]
    assert sum(url == FMP_ONE_MINUTE_URL for url, _ in session.requests) == 4


@pytest.mark.parametrize(('answer', 'error'), [
    (_FakeResponse({'Error Message': 'Invalid API KEY.'}, 401), ProviderAuthenticationError),
    (_FakeResponse({'Error Message': 'Restricted Endpoint'}, 402), ProviderEntitlementError),
    (_FakeResponse({'Error Message': 'Bandwidth limit exceeded, please upgrade'}, 429), ProviderQuotaError),
    (_FakeResponse({'Error Message': 'Restricted Endpoint: not available under your current subscription'}, 200), ProviderEntitlementError),
    (_FakeResponse(None, 302), Exception),
])
def test_provider_errors_map_to_typed_errors_without_retrying(answer, error):
    sleeps = []
    provider, session = _provider(FMPCommoditiesProvider, _commodity_handlers(lambda _: answer), sleeps)

    with pytest.raises(error) as raised:
        provider.fetch_candles(_request('GC-USD', '2026-07-06 00:00', '2026-07-07 00:00'))

    assert FAKE_KEY not in str(raised.value)
    assert sleeps == []
    assert sum(url == FMP_ONE_MINUTE_URL for url, _ in session.requests) == 1


def test_server_errors_are_retried_then_reported_unavailable():
    sleeps = []
    provider, _ = _provider(FMPCommoditiesProvider, _commodity_handlers(lambda _: _FakeResponse({}, 503)), sleeps)

    with pytest.raises(ProviderUnavailableError):
        provider.fetch_candles(_request('GC-USD', '2026-07-06 00:00', '2026-07-07 00:00'))

    assert sleeps == [1.0, 2.0, 4.0]


# ---------------------------------------------------------------------- key validation


@pytest.mark.parametrize(('status', 'payload', 'error'), [
    (200, [], None),
    (401, {'Error Message': 'Invalid API KEY.'}, ProviderAuthenticationError),
    (402, {'Error Message': 'Restricted Endpoint'}, ProviderEntitlementError),
    (200, {'Error Message': 'Restricted Endpoint'}, ProviderEntitlementError),
    (200, {'Error Message': 'Limit Reach . Please upgrade'}, ProviderRateLimitError),
    (503, None, ProviderUnavailableError),
])
def test_fmp_key_validation_reports_each_outcome(monkeypatch, status, payload, error):
    from jesse.services.historical_data import credential_validation

    class Response:
        status_code = status

        def json(self):
            return payload

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    seen = {}

    def fake_get(url, headers=None, params=None, **kwargs):
        seen.update(url=url, headers=headers, params=params, kwargs=kwargs)
        return Response()

    monkeypatch.setattr(credential_validation.requests, 'get', fake_get)

    if error is None:
        credential_validation.validate_fmp_api_key(FAKE_KEY)
    else:
        with pytest.raises(error):
            credential_validation.validate_fmp_api_key(FAKE_KEY)
    assert seen['url'] == credential_validation.FMP_CREDENTIAL_TEST_URL
    assert seen['headers'] == {'apikey': FAKE_KEY}
    assert FAKE_KEY not in str(seen['params'])
    assert seen['kwargs']['allow_redirects'] is False
