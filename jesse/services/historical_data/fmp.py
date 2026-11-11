"""
Financial Modeling Prep (FMP) historical candle providers.

FMP's one-minute chart endpoint has three quirks that shape everything below:

- Bars carry naive wall-clock strings in the market's own timezone: a stock or index in its
  listing exchange's zone, and crypto, forex and commodities in New York time. Converting them
  to UTC therefore needs the zone of every symbol, which FMP publishes per exchange.
- One call returns at most three calendar dates, counted back from `to`, whatever range was
  asked for. Each page is split into consecutive three-date windows so no bandwidth is spent
  on overlapping requests.
- A date FMP cannot parse is silently ignored and the most recent bars are returned instead,
  so bars outside the requested window are treated as a provider error rather than kept.
"""

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from math import isfinite
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from jesse.enums import data_providers, exchanges
from jesse.repositories import data_provider_credentials_repository

from .contracts import (
    AdjustmentMode,
    HistoricalCandle,
    HistoricalCandleBatch,
    HistoricalCandleProvider,
    HistoricalCandleRequest,
    ProviderCapabilities,
    SymbolCatalogEntry,
)
from .errors import (
    HistoricalCandleValidationError,
    HistoricalDataRequestError,
    ProviderAuthenticationError,
    ProviderEntitlementError,
    ProviderPaginationError,
    ProviderQuotaError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderSchemaError,
    ProviderSymbolNotFoundError,
    ProviderUnavailableError,
)


FMP_API_HOST = 'financialmodelingprep.com'
FMP_API_URL = f'https://{FMP_API_HOST}/stable'
FMP_ONE_MINUTE_URL = f'{FMP_API_URL}/historical-chart/1min'
FMP_FOUR_HOUR_URL = f'{FMP_API_URL}/historical-chart/4hour'
FMP_PROFILE_URL = f'{FMP_API_URL}/profile'
FMP_MARKET_HOURS_URL = f'{FMP_API_URL}/all-exchange-market-hours'
FMP_AVAILABLE_EXCHANGES_URL = f'{FMP_API_URL}/available-exchanges'
FMP_COMPANY_SYMBOLS_URL = f'{FMP_API_URL}/financial-statement-symbol-list'
FMP_ETF_LIST_URL = f'{FMP_API_URL}/etf-list'
FMP_FOREX_LIST_URL = f'{FMP_API_URL}/forex-list'
FMP_CRYPTO_LIST_URL = f'{FMP_API_URL}/cryptocurrency-list'
FMP_INDEX_LIST_URL = f'{FMP_API_URL}/index-list'
FMP_COMMODITIES_LIST_URL = f'{FMP_API_URL}/commodities-list'

# FMP answers a one-minute request with at most three calendar dates ending at `to`.
FMP_WINDOW_DATES = 3
# Thirty-day pages keep each committed import step comparable to Massive's 50,000-bar pages
# while splitting into eleven or twelve non-overlapping three-date windows.
FMP_PAGE_MINUTES = 30 * 1440
# A four-hour request covers about 180 days; 150-day windows stay inside that limit, so a
# forward scan never misses the first bar of a window.
FMP_FOUR_HOUR_SCAN_DAYS = 150
# Four attempts ride out one per-minute rate-limit window plus short network or server failures.
FMP_REQUEST_ATTEMPTS = 4
# Thirty seconds fits a three-day page; catalog lists are several megabytes and get longer.
FMP_REQUEST_TIMEOUT_SECONDS = 30
FMP_CATALOG_TIMEOUT_SECONDS = 120
# FMP's call limits refill every minute, so waiting longer than one window never helps.
FMP_MAX_RETRY_DELAY_SECONDS = 60.0
FMP_RATE_LIMIT_FALLBACK_SECONDS = 60.0
# Every pair of a dotted ticker is tried as a dot or a dash; real tickers have at most three dots.
FMP_MAX_SYMBOL_CANDIDATES = 8
FMP_SEARCH_LIMIT = 50

NEW_YORK = 'America/New_York'
# FMP stamps crypto, forex and commodity bars in New York time (verified against UTC exchange
# feeds, the CME daily break, and the Sunday forex open).
FMP_NEW_YORK_MARKETS_TIMEZONE = NEW_YORK
# Index exchanges FMP's market-hours table does not list, with the zone their bars use: S&P and
# Dow Jones indices and Cboe's VIX family open at 09:30 / 03:15 New York time, and the Nikkei
# indices follow Tokyo's session. Any other unlisted exchange is left out rather than guessed.
FMP_EXTRA_EXCHANGE_TIMEZONES: Mapping[str, str] = {
    'SNP': NEW_YORK,
    'DJI': NEW_YORK,
    'CXI': NEW_YORK,
    'OSA': 'Asia/Tokyo',
}
# Prices quoted in a currency's minor unit: London pence and Johannesburg cents. Upper-casing
# `GBp` would turn pence into pounds, so these are mapped to their market codes instead.
FMP_MINOR_CURRENCY_CODES: Mapping[str, str] = {
    'GBp': 'GBX',
    'ZAc': 'ZAC',
}
US_VENUE = 'US'


def _load_fmp_api_key() -> str:
    try:
        credentials = data_provider_credentials_repository.get_data_provider_credentials(data_providers.FMP)
    except ValueError as exc:
        raise ProviderAuthenticationError('Stored FMP API credentials are invalid') from exc
    api_key = credentials.get('api_key') if credentials is not None else None
    if not api_key:
        raise ProviderAuthenticationError('FMP API credentials are not configured')
    return api_key


@dataclass(frozen=True, slots=True)
class _ResolvedSymbol:
    """The FMP ticker behind one Jesse symbol and the zone its wall-clock bars are stamped in."""

    provider_symbol: str
    timezone: str


class FMPProvider(HistoricalCandleProvider):
    """Share FMP's chart, error and timezone handling across its candle sources."""

    provider_id = ''
    capabilities = ProviderCapabilities(
        credential_validation=True,
        ticker_search=True,
        native_timeframes=('1m',),
        max_candles_per_request=FMP_PAGE_MINUTES,
    )

    def __init__(
        self,
        credential_loader: Callable[[], str] | None = None,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._credential_loader = credential_loader or _load_fmp_api_key
        self._session = session or requests.Session()
        self._sleep = sleep
        self._resolved_symbols: dict[str, _ResolvedSymbol] = {}
        self._exchange_timezone_table: dict[str, str] | None = None

    # ------------------------------------------------------------------ candles

    def _fetch_candles(self, request: HistoricalCandleRequest) -> HistoricalCandleBatch:
        self._require_default_adjustment(request)
        api_key = self._credential_loader()
        resolved = self._resolve(request.symbol, api_key)
        zone = ZoneInfo(resolved.timezone)
        first_date, last_date = _local_dates(request, zone)

        candles_by_timestamp: dict[int, HistoricalCandle] = {}
        window_start = first_date
        while window_start <= last_date:
            window_end = min(window_start + timedelta(days=FMP_WINDOW_DATES - 1), last_date)
            payload = self._request_json(
                FMP_ONE_MINUTE_URL,
                api_key,
                {
                    'symbol': resolved.provider_symbol,
                    'from': window_start.isoformat(),
                    'to': window_end.isoformat(),
                    **self._chart_params(request),
                },
            )
            for candle in _normalize_bars(payload, request, zone, window_start, window_end):
                previous = candles_by_timestamp.get(candle.timestamp)
                if previous is not None and previous != candle:
                    raise ProviderSchemaError(
                        f'FMP returned conflicting candles for timestamp {candle.timestamp}'
                    )
                candles_by_timestamp[candle.timestamp] = candle
            window_start = window_end + timedelta(days=1)

        return HistoricalCandleBatch(
            request,
            tuple(candles_by_timestamp[timestamp] for timestamp in sorted(candles_by_timestamp)),
        )

    def find_earliest_available_timestamp(self, request: HistoricalCandleRequest) -> int | None:
        """
        Scan four-hour bars forward from the requested start to find where FMP's intraday history begins.

        A forward scan stays correct for delisted symbols and for histories with holes, where a
        bisection could skip real data. One-minute history never starts before four-hour history,
        and can start up to a few months later; the importer pages through that stretch.
        """
        self._require_default_adjustment(request)
        api_key = self._credential_loader()
        resolved = self._resolve(request.symbol, api_key)
        zone = ZoneInfo(resolved.timezone)
        first_date, last_date = _local_dates(request, zone)

        window_start = first_date
        while window_start <= last_date:
            window_end = min(window_start + timedelta(days=FMP_FOUR_HOUR_SCAN_DAYS - 1), last_date)
            payload = self._request_json(
                FMP_FOUR_HOUR_URL,
                api_key,
                {
                    'symbol': resolved.provider_symbol,
                    'from': window_start.isoformat(),
                    'to': window_end.isoformat(),
                    **self._chart_params(request),
                },
            )
            first_local_date = _earliest_bar_date(payload, window_start, window_end)
            if first_local_date is not None:
                # Four-hour bars begin at the regular open, so the day's first minute is used to
                # keep any earlier pre-market minutes of that day inside the import.
                day_start = datetime.combine(first_local_date, datetime.min.time(), zone)
                timestamp = int(day_start.astimezone(timezone.utc).timestamp()) * 1000
                return max(timestamp, request.requested_range.start_timestamp)
            window_start = window_end + timedelta(days=1)
        return None

    # ------------------------------------------------------------------ symbols

    def search_symbols(self, query: str, limit: int = FMP_SEARCH_LIMIT) -> tuple[str, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= FMP_SEARCH_LIMIT:
            raise HistoricalDataRequestError(f'FMP symbol search limit must be between 1 and {FMP_SEARCH_LIMIT}')
        normalized_query = query.strip().upper()
        if not normalized_query:
            return ()
        return tuple(
            entry.symbol
            for entry in self.list_symbol_entries()
            if entry.symbol.startswith(normalized_query)
            or (entry.name is not None and normalized_query in entry.name.upper())
        )[:limit]

    def list_symbols(self) -> tuple[str, ...]:
        return tuple(entry.symbol for entry in self.list_symbol_entries())

    def list_symbol_entries(self) -> tuple[SymbolCatalogEntry, ...]:
        api_key = self._credential_loader()
        entries = _without_collisions(self._catalog(api_key))
        if not entries:
            raise ProviderSchemaError(f'FMP returned an empty {self.provider_id} catalog')
        return tuple(entries[symbol][1] for symbol in sorted(entries))

    def _resolve(self, symbol: str, api_key: str) -> _ResolvedSymbol:
        normalized_symbol = symbol.strip().upper()
        cached = self._resolved_symbols.get(normalized_symbol)
        if cached is None:
            cached = self._resolve_symbol(normalized_symbol, api_key)
            self._resolved_symbols[normalized_symbol] = cached
        return cached

    def _resolve_from_catalog(self, symbol: str, api_key: str) -> _ResolvedSymbol:
        """Resolve through the provider's own catalog, which is small for every source but stocks."""
        matches = [
            resolved
            for jesse_symbol, (resolved, _) in self._catalog(api_key)
            if jesse_symbol == symbol
        ]
        if not matches:
            raise ProviderSymbolNotFoundError(f'{self.provider_id} has no symbol {symbol!r}')
        if len({match.provider_symbol for match in matches}) != 1:
            raise ProviderSymbolNotFoundError(
                f'{symbol!r} matches more than one FMP ticker on {self.provider_id}, so it cannot be imported'
            )
        return matches[0]

    def _exchange_timezone(self, exchange: str | None, api_key: str) -> str | None:
        if not exchange:
            return None
        if self._exchange_timezone_table is None:
            self._exchange_timezone_table = self._load_exchange_timezones(api_key)
        return self._exchange_timezone_table.get(exchange.strip().upper())

    def _load_exchange_timezones(self, api_key: str) -> dict[str, str]:
        payload = self._request_json(FMP_MARKET_HOURS_URL, api_key, None)
        table = dict(FMP_EXTRA_EXCHANGE_TIMEZONES)
        for row in _list_of_objects(payload, 'market-hours'):
            exchange = _optional_text(row, 'exchange')
            zone = _optional_text(row, 'timezone')
            if exchange and zone and _is_known_timezone(zone):
                # FMP's own table wins over the fallbacks for any exchange it lists.
                table[exchange.upper()] = zone
        return table

    def _require_default_adjustment(self, request: HistoricalCandleRequest) -> None:
        if request.adjustment_mode is not self.capabilities.default_adjustment_mode:
            raise HistoricalDataRequestError(
                f'{self.provider_id} requires {self.capabilities.default_adjustment_mode.value} candles'
            )

    def _chart_params(self, request: HistoricalCandleRequest) -> dict[str, str]:
        return {}

    def _resolve_symbol(self, symbol: str, api_key: str) -> _ResolvedSymbol:
        raise NotImplementedError

    def _catalog(self, api_key: str) -> list[tuple[str, tuple[_ResolvedSymbol, SymbolCatalogEntry]]]:
        """Return `(jesse_symbol, (resolved, entry))` pairs, collisions included."""
        raise NotImplementedError

    # ------------------------------------------------------------------ transport

    def _request_json(
        self,
        url: str,
        api_key: str,
        params: dict[str, str] | None,
        timeout: float = FMP_REQUEST_TIMEOUT_SECONDS,
    ) -> Any:
        for attempt in range(FMP_REQUEST_ATTEMPTS):
            is_last_attempt = attempt + 1 == FMP_REQUEST_ATTEMPTS
            try:
                # The key travels in a header so it never appears in URLs, logs or exception text.
                response = self._session.get(
                    url,
                    headers={'apikey': api_key},
                    params=params,
                    timeout=timeout,
                    allow_redirects=False,
                )
            except requests.RequestException as exc:
                if is_last_attempt:
                    raise ProviderUnavailableError('FMP is currently unavailable') from exc
                self._sleep(2 ** attempt)
                continue

            try:
                payload = _response_payload(response)
                error = _response_error(response.status_code, payload)
                if error is None:
                    return payload
                if isinstance(error, ProviderRateLimitError):
                    if is_last_attempt:
                        raise ProviderRateLimitError(
                            'FMP is still refusing requests after waiting; the plan\'s per-minute limit '
                            'or its bandwidth allowance may be used up'
                        )
                    self._sleep(_retry_delay(response.headers.get('Retry-After'), FMP_RATE_LIMIT_FALLBACK_SECONDS))
                    continue
                if isinstance(error, ProviderUnavailableError) and not is_last_attempt:
                    self._sleep(_retry_delay(response.headers.get('Retry-After'), float(2 ** attempt)))
                    continue
                raise error
            finally:
                response.close()

        raise ProviderUnavailableError('FMP is currently unavailable')


class FMPStocksProvider(FMPProvider):
    """Stocks and ETFs on every exchange FMP covers, split-adjusted, with pre- and after-market bars."""

    provider_id = exchanges.FMP_STOCKS
    capabilities = ProviderCapabilities(
        credential_validation=True,
        ticker_search=True,
        native_timeframes=('1m',),
        adjustment_modes=(AdjustmentMode.SPLIT_ADJUSTED,),
        max_candles_per_request=FMP_PAGE_MINUTES,
        default_adjustment_mode=AdjustmentMode.SPLIT_ADJUSTED,
    )

    def _chart_params(self, request: HistoricalCandleRequest) -> dict[str, str]:
        # Jesse keeps every observed bar, so US pre-market and after-hours minutes are requested;
        # other exchanges ignore the flag. FMP's default prices are split-adjusted.
        return {'extended': 'true'}

    def _resolve_symbol(self, symbol: str, api_key: str) -> _ResolvedSymbol:
        base, quote_asset = _split_symbol(symbol, self.provider_id)
        listings = []
        for candidate in _stock_ticker_candidates(base):
            payload = self._request_json(FMP_PROFILE_URL, api_key, {'symbol': candidate})
            for profile in _list_of_objects(payload, 'profile'):
                if _optional_text(profile, 'symbol') == candidate:
                    listings.append((candidate, profile))
        if not listings:
            raise ProviderSymbolNotFoundError(f'FMP has no stock or ETF {base!r}')

        matching = [
            (candidate, profile)
            for candidate, profile in listings
            if _jesse_currency(_optional_text(profile, 'currency')) == quote_asset
        ]
        if not matching:
            candidate, profile = listings[0]
            currency = _jesse_currency(_optional_text(profile, 'currency'))
            if currency is None:
                raise ProviderSymbolNotFoundError(f'FMP does not report a usable trading currency for {candidate!r}')
            raise ProviderSymbolNotFoundError(
                f'FMP prices {candidate} in {currency}; import it as {base}-{currency}'
            )
        if len(matching) > 1:
            raise ProviderSymbolNotFoundError(
                f'{symbol!r} matches more than one FMP listing ({", ".join(c for c, _ in matching)}), '
                'so it cannot be imported'
            )

        candidate, profile = matching[0]
        exchange = _optional_text(profile, 'exchange')
        zone = self._exchange_timezone(exchange, api_key)
        if zone is None:
            raise ProviderSchemaError(f'FMP does not publish a timezone for exchange {exchange!r} of {candidate}')
        return _ResolvedSymbol(candidate, zone)

    def _catalog(self, api_key: str) -> list[tuple[str, tuple[_ResolvedSymbol, SymbolCatalogEntry]]]:
        companies = _list_of_objects(
            self._request_json(FMP_COMPANY_SYMBOLS_URL, api_key, None, FMP_CATALOG_TIMEOUT_SECONDS),
            'company symbol',
        )
        etfs = _list_of_objects(
            self._request_json(FMP_ETF_LIST_URL, api_key, None, FMP_CATALOG_TIMEOUT_SECONDS),
            'ETF',
        )
        venues = _suffix_venues(_list_of_objects(
            self._request_json(FMP_AVAILABLE_EXCHANGES_URL, api_key, None),
            'exchange',
        ))

        etf_symbols = {
            ticker for row in etfs if (ticker := _optional_text(row, 'symbol')) is not None
        }
        listings: dict[str, tuple[str, str | None]] = {}
        for row in companies:
            ticker = _optional_text(row, 'symbol')
            currency = _jesse_currency(_optional_text(row, 'tradingCurrency'))
            if ticker is not None and currency is not None:
                listings[ticker] = (currency, _optional_text(row, 'companyName'))
        for row in etfs:
            ticker = _optional_text(row, 'symbol')
            # FMP's ETF list has no currency; only US listings are known to trade in dollars, so
            # ETFs on other exchanges are left out instead of being given a guessed currency.
            if ticker is not None and ticker not in listings and '.' not in ticker:
                listings[ticker] = ('USD', _optional_text(row, 'name'))

        pairs = []
        for ticker, (currency, name) in listings.items():
            jesse_base = _jesse_stock_base(ticker)
            if jesse_base is None:
                continue
            symbol = f'{jesse_base}-{currency}'
            # The zone is only needed at import time, where it is resolved through the profile.
            resolved = _ResolvedSymbol(ticker, '')
            pairs.append((symbol, (resolved, SymbolCatalogEntry(
                symbol,
                name=name,
                kind='ETF' if ticker in etf_symbols else 'Stock',
                venue=venues.get(_ticker_suffix(ticker), US_VENUE if _ticker_suffix(ticker) is None else None),
            ))))
        return pairs


class FMPCurrenciesProvider(FMPProvider):
    """Forex pairs and crypto coins quoted in dollars, stamped in New York time."""

    provider_id = exchanges.FMP_CURRENCIES

    def _resolve_symbol(self, symbol: str, api_key: str) -> _ResolvedSymbol:
        _split_symbol(symbol, self.provider_id)
        return self._resolve_from_catalog(symbol, api_key)

    def _catalog(self, api_key: str) -> list[tuple[str, tuple[_ResolvedSymbol, SymbolCatalogEntry]]]:
        forex = _list_of_objects(
            self._request_json(FMP_FOREX_LIST_URL, api_key, None, FMP_CATALOG_TIMEOUT_SECONDS),
            'forex',
        )
        crypto = _list_of_objects(
            self._request_json(FMP_CRYPTO_LIST_URL, api_key, None, FMP_CATALOG_TIMEOUT_SECONDS),
            'crypto',
        )
        pairs = []
        for row in forex:
            ticker = _optional_text(row, 'symbol')
            base = _optional_text(row, 'fromCurrency')
            quote_asset = _optional_text(row, 'toCurrency')
            if not ticker or not base or not quote_asset or ticker != f'{base}{quote_asset}':
                continue
            if not _is_plain_code(base) or not _is_plain_code(quote_asset):
                continue
            from_name = _optional_text(row, 'fromName')
            to_name = _optional_text(row, 'toName')
            symbol = f'{base}-{quote_asset}'
            pairs.append((symbol, (
                _ResolvedSymbol(ticker, FMP_NEW_YORK_MARKETS_TIMEZONE),
                SymbolCatalogEntry(
                    symbol,
                    name=f'{from_name} / {to_name}' if from_name and to_name else None,
                    kind='Forex',
                ),
            )))
        for row in crypto:
            ticker = _optional_text(row, 'symbol')
            # Every coin FMP lists is quoted in dollars; the two exceptions lack that suffix.
            if not ticker or not ticker.endswith('USD') or not _is_plain_code(ticker[:-3]):
                continue
            symbol = f'{ticker[:-3]}-USD'
            pairs.append((symbol, (
                _ResolvedSymbol(ticker, FMP_NEW_YORK_MARKETS_TIMEZONE),
                SymbolCatalogEntry(symbol, name=_optional_text(row, 'name'), kind='Crypto'),
            )))
        return pairs


class FMPIndicesProvider(FMPProvider):
    """Stock-market, volatility and yield indices in their home exchange's timezone."""

    provider_id = exchanges.FMP_INDICES

    def _resolve_symbol(self, symbol: str, api_key: str) -> _ResolvedSymbol:
        _split_symbol(symbol, self.provider_id)
        return self._resolve_from_catalog(symbol, api_key)

    def _catalog(self, api_key: str) -> list[tuple[str, tuple[_ResolvedSymbol, SymbolCatalogEntry]]]:
        indices = _list_of_objects(self._request_json(FMP_INDEX_LIST_URL, api_key, None), 'index')
        pairs = []
        for row in indices:
            ticker = _optional_text(row, 'symbol')
            currency = _jesse_currency(_optional_text(row, 'currency'))
            zone = self._exchange_timezone(_optional_text(row, 'exchange'), api_key)
            if not ticker or currency is None or zone is None:
                continue
            jesse_base = _jesse_stock_base(ticker[1:] if ticker.startswith('^') else ticker)
            if jesse_base is None:
                continue
            symbol = f'{jesse_base}-{currency}'
            pairs.append((symbol, (
                _ResolvedSymbol(ticker, zone),
                SymbolCatalogEntry(symbol, name=_optional_text(row, 'name'), kind='Index'),
            )))
        return pairs


class FMPCommoditiesProvider(FMPProvider):
    """Continuous front-month commodity, rate and index futures, stamped in New York time."""

    provider_id = exchanges.FMP_COMMODITIES

    def _resolve_symbol(self, symbol: str, api_key: str) -> _ResolvedSymbol:
        _split_symbol(symbol, self.provider_id)
        return self._resolve_from_catalog(symbol, api_key)

    def _catalog(self, api_key: str) -> list[tuple[str, tuple[_ResolvedSymbol, SymbolCatalogEntry]]]:
        commodities = _list_of_objects(self._request_json(FMP_COMMODITIES_LIST_URL, api_key, None), 'commodity')
        pairs = []
        for row in commodities:
            ticker = _optional_text(row, 'symbol')
            currency = _optional_text(row, 'currency')
            # Tickers are the contract root followed by the price currency, which is `USX` (US
            # cents) for grains, softs and livestock.
            if not ticker or not currency or not ticker.endswith(currency) or not _is_plain_code(currency):
                continue
            root = ticker[:-len(currency)]
            if not _is_plain_code(root):
                continue
            symbol = f'{root}-{currency}'
            pairs.append((symbol, (
                _ResolvedSymbol(ticker, FMP_NEW_YORK_MARKETS_TIMEZONE),
                SymbolCatalogEntry(symbol, name=_optional_text(row, 'name'), kind='Future'),
            )))
        return pairs


# ---------------------------------------------------------------------- helpers


def _split_symbol(symbol: str, provider_id: str) -> tuple[str, str]:
    parts = symbol.split('-')
    if len(parts) != 2 or not all(parts):
        raise HistoricalDataRequestError(f'{provider_id} symbols must use the BASE-QUOTE format')
    return parts[0], parts[1]


def _stock_ticker_candidates(base: str) -> tuple[str, ...]:
    """
    FMP tickers a Jesse stock base can stand for.

    Jesse symbols allow a single dash, so FMP's share-class dashes (`BRK-B`, `VOLV-B.ST`) become
    dots, while FMP's own dots mark exchange suffixes. Each dot may therefore have been a dash;
    the exact spelling is tried first.
    """
    parts = base.split('.')
    candidates = []
    for mask in range(2 ** (len(parts) - 1)):
        ticker = parts[0]
        for index, part in enumerate(parts[1:]):
            ticker += ('-' if mask >> index & 1 else '.') + part
        candidates.append(ticker)
        if len(candidates) == FMP_MAX_SYMBOL_CANDIDATES:
            break
    return tuple(candidates)


def _jesse_stock_base(ticker: str) -> str | None:
    """Spell an FMP ticker as a Jesse base, or None when it cannot be represented."""
    base = ticker.strip().upper().replace('-', '.')
    if not base or base.startswith('.') or base.endswith('.') or '..' in base:
        return None
    if not all(character.isalnum() or character in '.&' for character in base):
        return None
    return base


def _jesse_currency(currency: str | None) -> str | None:
    if currency is None:
        return None
    if currency in FMP_MINOR_CURRENCY_CODES:
        return FMP_MINOR_CURRENCY_CODES[currency]
    if currency != currency.upper() or not _is_plain_code(currency):
        # An unknown mixed-case code is another minor unit; upper-casing it would mislabel prices.
        return None
    return currency


def _is_plain_code(value: str) -> bool:
    return bool(value) and value.isascii() and value.isalnum() and value == value.upper()


def _ticker_suffix(ticker: str) -> str | None:
    return f'.{ticker.rsplit(".", 1)[1]}' if '.' in ticker else None


def _suffix_venues(rows: tuple[Mapping[str, Any], ...]) -> dict[str | None, str]:
    venues: dict[str | None, str] = {}
    for row in rows:
        suffix = _optional_text(row, 'symbolSuffix')
        name = _optional_text(row, 'name')
        if suffix and suffix.startswith('.') and name:
            venues[suffix.upper()] = name
    return venues


def _without_collisions(
    pairs: list[tuple[str, tuple[_ResolvedSymbol, SymbolCatalogEntry]]],
) -> dict[str, tuple[_ResolvedSymbol, SymbolCatalogEntry]]:
    """Drop Jesse symbols that two FMP tickers map to, since an import could not tell them apart."""
    entries: dict[str, tuple[_ResolvedSymbol, SymbolCatalogEntry]] = {}
    ambiguous = set()
    for symbol, value in pairs:
        previous = entries.get(symbol)
        if previous is not None and previous[0].provider_symbol != value[0].provider_symbol:
            ambiguous.add(symbol)
            continue
        entries.setdefault(symbol, value)
    for symbol in ambiguous:
        entries.pop(symbol, None)
    return entries


def _is_known_timezone(zone: str) -> bool:
    try:
        ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def _local_dates(request: HistoricalCandleRequest, zone: ZoneInfo) -> tuple[date, date]:
    """Local calendar dates covering the half-open UTC range of a request."""
    start = datetime.fromtimestamp(request.requested_range.start_timestamp / 1000, timezone.utc)
    last = datetime.fromtimestamp((request.requested_range.end_timestamp - 1) / 1000, timezone.utc)
    return start.astimezone(zone).date(), last.astimezone(zone).date()


def _parse_local_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ProviderSchemaError('FMP bar dates must be strings')
    try:
        return datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
    except ValueError as exc:
        raise ProviderSchemaError('FMP returned an unreadable bar date') from exc


def _utc_timestamp(local_time: datetime, zone: ZoneInfo) -> int | None:
    """
    Convert a wall-clock bar time to UTC milliseconds, or None for a time the zone skips.

    The repeated hour at the end of daylight saving resolves to its first occurrence, which
    is the copy FMP keeps (verified against a UTC exchange feed).
    """
    aware = local_time.replace(tzinfo=zone)
    utc_time = aware.astimezone(timezone.utc)
    if utc_time.astimezone(zone).replace(tzinfo=None) != local_time:
        return None
    return int(utc_time.timestamp()) * 1000


def _normalize_bars(
    payload: Any,
    request: HistoricalCandleRequest,
    zone: ZoneInfo,
    window_start: date,
    window_end: date,
) -> tuple[HistoricalCandle, ...]:
    rows = _list_of_objects(payload, 'candle')
    candles = []
    try:
        for row in rows:
            local_time = _parse_local_time(row.get('date'))
            if not window_start <= local_time.date() <= window_end:
                # FMP answers dates it cannot use with the latest bars; keeping them would hide a gap.
                raise ProviderSchemaError('FMP returned candles outside the requested dates')
            if local_time.second or local_time.microsecond:
                # A one-minute bar cannot start mid-minute. FMP's history holds a few such rows (31 of
                # 288,520 for Saudi Aramco), each a zero-volume flat price snapshot, so no trade is lost.
                continue
            timestamp = _utc_timestamp(local_time, zone)
            if timestamp is None:
                # No market prints at a wall-clock time that daylight saving skips.
                continue
            if not request.requested_range.start_timestamp <= timestamp < request.requested_range.end_timestamp:
                continue
            volume = row.get('volume')
            open_price = _number(row.get('open'), 'open')
            high = _number(row.get('high'), 'high')
            low = _number(row.get('low'), 'low')
            close = _number(row.get('close'), 'close')
            if high < low:
                raise ProviderSchemaError('FMP returned a candle whose high is below its low')
            candles.append(HistoricalCandle(
                timestamp=timestamp,
                open=open_price,
                # Some early bars (Saudi Aramco's first days, for one) report an open or close a
                # tick outside their high and low. Both are trades inside that minute, so the true
                # range must include them; widening it is the smallest correction the bar proves.
                high=max(high, open_price, close),
                low=min(low, open_price, close),
                close=close,
                # Some index bars carry no volume; zero records that absence.
                volume=0.0 if volume is None else _number(volume, 'volume'),
            ))
    except ProviderSchemaError:
        raise
    except (HistoricalCandleValidationError, TypeError, ValueError) as exc:
        raise ProviderSchemaError('FMP returned an invalid candle') from exc
    return tuple(candles)


def _earliest_bar_date(payload: Any, window_start: date, window_end: date) -> date | None:
    dates = []
    for row in _list_of_objects(payload, 'candle'):
        local_date = _parse_local_time(row.get('date')).date()
        if not window_start <= local_date <= window_end:
            raise ProviderSchemaError('FMP returned candles outside the requested dates')
        dates.append(local_date)
    return min(dates) if dates else None


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ProviderSchemaError(f'FMP {field} must be a finite number')
    return float(value)


def _optional_text(row: Mapping[str, Any], key: str) -> str | None:
    value = row.get(key)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _list_of_objects(payload: Any, label: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(payload, list):
        raise ProviderSchemaError(f'FMP {label} results must be an array')
    if any(not isinstance(row, Mapping) for row in payload):
        raise ProviderSchemaError(f'FMP {label} entries must be objects')
    return tuple(payload)


def _response_payload(response: requests.Response) -> Any:
    try:
        return response.json()
    except requests.exceptions.JSONDecodeError as exc:
        if 200 <= response.status_code < 300:
            raise ProviderSchemaError('FMP returned invalid JSON') from exc
        return None


def _error_message(payload: Any) -> str:
    if isinstance(payload, Mapping):
        for key in ('Error Message', 'error', 'message'):
            value = payload.get(key)
            if isinstance(value, str):
                return value.lower()
    return ''


def _response_error(status_code: int, payload: Any) -> Exception | None:
    message = _error_message(payload)
    if 200 <= status_code < 300:
        if isinstance(payload, Mapping) and 'Error Message' in payload:
            # Some plan limits arrive as a successful status carrying an error object.
            return _limit_error(message) or _plan_error(message) or ProviderRequestError(
                'FMP could not complete the request'
            )
        return None
    if status_code == 401:
        return ProviderAuthenticationError('FMP rejected the API key')
    if status_code in (402, 403):
        return ProviderEntitlementError('Your FMP plan does not include the requested data')
    if status_code == 404:
        return ProviderSymbolNotFoundError('FMP could not find the requested data')
    if status_code == 429:
        return _limit_error(message) or ProviderRateLimitError('FMP rate limit reached')
    if 300 <= status_code < 400:
        return ProviderPaginationError('FMP attempted an unexpected redirect')
    if status_code >= 500:
        return ProviderUnavailableError('FMP is currently unavailable')
    return ProviderRequestError('FMP rejected the request')


def _limit_error(message: str) -> Exception | None:
    """
    Classify a limit message. FMP's per-minute call limit answers 429 with "Limit Reach . Please
    upgrade your plan" and no Retry-After, so that wording is a wait-and-retry, never a quota;
    only an explicit bandwidth message means the plan's allowance will not refill within minutes.
    """
    if 'bandwidth' in message:
        return ProviderQuotaError('Your FMP plan has used its bandwidth allowance for now')
    if 'limit' in message:
        return ProviderRateLimitError('FMP rate limit reached')
    return None


def _plan_error(message: str) -> Exception | None:
    if 'restricted' in message or 'subscription' in message:
        return ProviderEntitlementError('Your FMP plan does not include the requested data')
    return None


def _retry_delay(retry_after: str | None, fallback: float) -> float:
    delay = fallback
    if retry_after:
        try:
            delay = float(retry_after)
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                delay = (retry_at - datetime.now(timezone.utc)).total_seconds()
            except (TypeError, ValueError, OverflowError):
                delay = fallback
    if not isfinite(delay):
        delay = fallback
    return min(max(delay, 0.0), FMP_MAX_RETRY_DELAY_SECONDS)
