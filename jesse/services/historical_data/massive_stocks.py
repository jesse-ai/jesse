import hashlib
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from math import isfinite
from threading import Lock
from typing import Any
from urllib.parse import parse_qsl, quote, urlparse

import requests

from jesse.enums import data_providers, exchanges
from jesse.repositories import data_provider_credentials_repository
from jesse.services.redis import sync_redis

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
    ProviderRangeError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderSchemaError,
    ProviderSymbolNotFoundError,
    ProviderUnavailableError,
)


MASSIVE_API_HOST = 'api.massive.com'
MASSIVE_AGGREGATES_URL = f'https://{MASSIVE_API_HOST}/v2/aggs/ticker'
MASSIVE_TICKERS_URL = f'https://{MASSIVE_API_HOST}/v3/reference/tickers'
MASSIVE_FUTURES_CONTRACTS_URL = f'https://{MASSIVE_API_HOST}/futures/v1/contracts'
MASSIVE_FUTURES_PRODUCTS_URL = f'https://{MASSIVE_API_HOST}/futures/v1/products'
MASSIVE_FUTURES_AGGREGATES_URL = f'https://{MASSIVE_API_HOST}/futures/v1/aggs'
# Massive documents 50,000 as the custom-aggregate endpoint's maximum base-bar page size.
MASSIVE_PAGE_LIMIT = 50_000
# Three attempts cover short network/server failures without making a synchronous import stall indefinitely.
MASSIVE_REQUEST_ATTEMPTS = 3
# Thirty seconds accommodates large aggregate pages while bounding an unavailable provider call.
MASSIVE_REQUEST_TIMEOUT_SECONDS = 30
# Massive's advertised entry-level quota refills each minute, so longer server delays are not useful here.
MASSIVE_MAX_RETRY_DELAY_SECONDS = 60.0
# At 50,000 base bars per page, 1,000 pages exceed the provider's complete stock-minute history.
MASSIVE_MAX_PAGES = 1_000
# Free plans allow five requests per minute; paid plans stay unpaced until Massive reports a 429.
MASSIVE_FREE_REQUEST_INTERVAL_SECONDS = 12.0
# Without Retry-After, wait for the documented free-tier window to reset before retrying.
MASSIVE_RATE_LIMIT_FALLBACK_SECONDS = 60.0
# A continuously used free-tier marker stays alive; idle or replaced credentials are probed again later.
MASSIVE_RATE_LIMIT_STATE_TTL_SECONDS = 3_600
# Fifty responsive selector results avoid downloading Massive's full equity catalog on every search.
MASSIVE_TICKER_SEARCH_LIMIT = 50

# Massive's equity `type` codes, spelled out so the Dashboard can show them without a legend.
MASSIVE_STOCK_TYPE_LABELS: Mapping[str, str] = {
    'CS': 'Common Stock',
    'PFD': 'Preferred Stock',
    'WARRANT': 'Warrant',
    'RIGHT': 'Right',
    'BOND': 'Bond',
    'ETF': 'ETF',
    'ETN': 'ETN',
    'ETV': 'ETV',
    'ETS': 'Single-Security ETF',
    'SP': 'Structured Product',
    'ADRC': 'ADR',
    'ADRP': 'ADR Preferred',
    'ADRR': 'ADR Right',
    'ADRW': 'ADR Warrant',
    'FUND': 'Fund',
    'BASKET': 'Basket',
    'UNIT': 'Unit',
    'LT': 'Liquidating Trust',
    'OS': 'Ordinary Shares',
    'GDR': 'GDR',
    'NYRS': 'NY Registry Shares',
    'AGEN': 'Agency Bond',
    'EQLK': 'Equity-Linked Bond',
    'OTHER': 'Other',
}
# ISO 10383 market identifier codes Massive reports for the venues Jesse users meet most often.
MASSIVE_VENUE_LABELS: Mapping[str, str] = {
    'XNAS': 'NASDAQ',
    'XNYS': 'NYSE',
    'ARCX': 'NYSE Arca',
    'XASE': 'NYSE American',
    'BATS': 'Cboe BZX',
    'XCBO': 'Cboe',
    'XNYM': 'NYMEX',
    'XCME': 'CME',
    'XCBT': 'CBOT',
    'XCEC': 'COMEX',
}

# Provider instances share process-local pacing so concurrent calls to one Massive product respect
# a detected free-tier limit without slowing unrelated paid products.
_massive_request_schedule: dict[str, tuple[float, float]] = {}
_massive_request_schedule_lock = Lock()


def _load_massive_api_key() -> str:
    try:
        credentials = data_provider_credentials_repository.get_data_provider_credentials(data_providers.MASSIVE)
    except ValueError as exc:
        raise ProviderAuthenticationError('Stored Massive API credentials are invalid') from exc
    api_key = credentials.get('api_key') if credentials is not None else None
    if not api_key:
        raise ProviderAuthenticationError('Massive API credentials are not configured')
    return api_key


class MassiveAggregatesProvider(HistoricalCandleProvider):
    """Share Massive's millisecond aggregate and reference APIs across supported markets."""

    provider_id = ''
    markets: tuple[str, ...] = ()
    supports_adjustment = False
    capabilities = ProviderCapabilities(max_candles_per_request=MASSIVE_PAGE_LIMIT)

    def __init__(
        self,
        credential_loader: Callable[[], str] | None = None,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        wall_time: Callable[[], float] = time.time,
    ) -> None:
        self._credential_loader = credential_loader or _load_massive_api_key
        # Injected sessions are fixture boundaries and should not touch the application's Redis limiter.
        self._use_shared_rate_limit = session is None
        self._session = session or requests.Session()
        self._sleep = sleep
        self._monotonic = monotonic
        self._wall_time = wall_time

    def _fetch_candles(self, request: HistoricalCandleRequest) -> HistoricalCandleBatch:
        if request.adjustment_mode is not self.capabilities.default_adjustment_mode:
            raise HistoricalDataRequestError(
                f'{self.provider_id} requires {self.capabilities.default_adjustment_mode.value} candles'
            )
        api_key = self._credential_loader()
        provider_symbol = self._provider_symbol(request.symbol, api_key)
        url = _aggregate_url(provider_symbol, request)
        params: dict[str, str | int] | None = {
            'sort': 'asc',
            'limit': MASSIVE_PAGE_LIMIT,
        }
        if self.supports_adjustment:
            params['adjusted'] = (
                'true' if request.adjustment_mode is AdjustmentMode.SPLIT_ADJUSTED else 'false'
            )
        candles_by_timestamp: dict[int, HistoricalCandle] = {}
        visited_urls: set[str] = set()

        for _ in range(MASSIVE_MAX_PAGES):
            if url in visited_urls:
                raise ProviderPaginationError('Massive returned a repeated pagination URL')
            visited_urls.add(url)

            payload = self._request_json(url, api_key, params)
            page_candles = _normalize_page(
                payload,
                request,
                provider_symbol,
                expected_adjusted=(
                    request.adjustment_mode is AdjustmentMode.SPLIT_ADJUSTED
                    if self.supports_adjustment
                    else None
                ),
            )
            for candle in page_candles:
                previous = candles_by_timestamp.get(candle.timestamp)
                if previous is not None and previous != candle:
                    raise ProviderPaginationError(
                        f'Massive returned conflicting candles for timestamp {candle.timestamp}'
                    )
                candles_by_timestamp[candle.timestamp] = candle

            next_url = payload.get('next_url')
            if next_url is None:
                candles = tuple(candles_by_timestamp[timestamp] for timestamp in sorted(candles_by_timestamp))
                return HistoricalCandleBatch(request, candles)
            url = _validated_next_url(next_url)
            params = None

        raise ProviderPaginationError('Massive pagination exceeded the safety limit')

    def find_earliest_available_timestamp(self, request: HistoricalCandleRequest) -> int | None:
        """Probe one ascending aggregate so Massive's actual entitlement defines the import start."""
        if request.adjustment_mode is not self.capabilities.default_adjustment_mode:
            raise HistoricalDataRequestError(
                f'{self.provider_id} requires {self.capabilities.default_adjustment_mode.value} candles'
            )
        api_key = self._credential_loader()
        provider_symbol = self._provider_symbol(request.symbol, api_key)
        params: dict[str, str | int] = {'sort': 'asc', 'limit': 1}
        if self.supports_adjustment:
            params['adjusted'] = (
                'true' if request.adjustment_mode is AdjustmentMode.SPLIT_ADJUSTED else 'false'
            )
        payload = self._request_json(_aggregate_url(provider_symbol, request), api_key, params)
        candles = _normalize_page(
            payload,
            request,
            provider_symbol,
            expected_adjusted=(
                request.adjustment_mode is AdjustmentMode.SPLIT_ADJUSTED
                if self.supports_adjustment
                else None
            ),
        )
        return candles[0].timestamp if candles else None

    def search_symbols(self, query: str, limit: int = MASSIVE_TICKER_SEARCH_LIMIT) -> tuple[str, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MASSIVE_TICKER_SEARCH_LIMIT:
            raise HistoricalDataRequestError(
                f'Massive ticker search limit must be between 1 and {MASSIVE_TICKER_SEARCH_LIMIT}'
            )
        api_key = self._credential_loader()
        params: dict[str, str | int] = {
            'active': 'true',
            'search': query.strip(),
            'sort': 'ticker',
            'order': 'asc',
            'limit': limit,
        }
        if len(self.markets) == 1:
            params['market'] = self.markets[0]
        payload = self._request_json(MASSIVE_TICKERS_URL, api_key, params)
        return tuple(entry.symbol for entry in _normalize_ticker_search(payload, self.markets, self._catalog_entry))

    def list_symbols(self) -> tuple[str, ...]:
        return tuple(entry.symbol for entry in self.list_symbol_entries())

    def list_symbol_entries(self) -> tuple[SymbolCatalogEntry, ...]:
        api_key = self._credential_loader()
        entries: dict[str, SymbolCatalogEntry] = {}
        symbol_markets: dict[str, str] = {}
        ambiguous_symbols = set()
        for market in self.markets:
            url = MASSIVE_TICKERS_URL
            params: dict[str, str | int] | None = {
                'market': market,
                'active': 'true',
                'sort': 'ticker',
                'order': 'asc',
                # Massive's 1,000-result maximum keeps complete catalog retrieval bounded.
                'limit': 1_000,
            }
            visited_urls = set()
            for _ in range(MASSIVE_MAX_PAGES):
                if url in visited_urls:
                    raise ProviderPaginationError('Massive returned a repeated ticker pagination URL')
                visited_urls.add(url)
                payload = self._request_json(url, api_key, params)
                for entry in _normalize_ticker_search(payload, self.markets, self._catalog_entry):
                    previous_market = symbol_markets.get(entry.symbol)
                    if previous_market is not None and previous_market != market:
                        # Jesse's BASE-QUOTE form cannot distinguish a fiat pair from a crypto token
                        # with the same code, so omit only that collision instead of losing the catalog.
                        ambiguous_symbols.add(entry.symbol)
                        continue
                    if entry.symbol not in entries:
                        entries[entry.symbol] = entry
                        symbol_markets[entry.symbol] = market
                next_url = payload.get('next_url')
                if next_url is None:
                    break
                url = _validated_next_url(next_url)
                params = None
            else:
                raise ProviderPaginationError('Massive ticker pagination exceeded the safety limit')
        if not entries:
            raise ProviderSchemaError(f'Massive returned an empty active-{",".join(self.markets)} catalog')
        return tuple(entries[symbol] for symbol in sorted(entries) if symbol not in ambiguous_symbols)

    def _request_json(
        self,
        url: str,
        api_key: str,
        params: dict[str, str | int] | None,
    ) -> Mapping[str, Any]:
        for attempt in range(MASSIVE_REQUEST_ATTEMPTS):
            self._wait_for_request_slot(api_key)
            try:
                response = self._session.get(
                    url,
                    headers={'Authorization': f'Bearer {api_key}'},
                    params=params,
                    timeout=MASSIVE_REQUEST_TIMEOUT_SECONDS,
                    allow_redirects=False,
                )
            except requests.RequestException as exc:
                if attempt + 1 == MASSIVE_REQUEST_ATTEMPTS:
                    raise ProviderUnavailableError('Massive is currently unavailable') from exc
                self._sleep(2 ** attempt)
                continue

            try:
                payload = _response_payload(response)
                error = _response_error(response.status_code, payload)
                if error is None:
                    return payload
                if isinstance(error, ProviderQuotaError):
                    raise error
                if isinstance(error, ProviderRateLimitError):
                    self._activate_free_tier_pacing(api_key, response.headers.get('Retry-After'))
                    if attempt + 1 < MASSIVE_REQUEST_ATTEMPTS:
                        continue
                elif response.status_code >= 500:
                    if attempt + 1 < MASSIVE_REQUEST_ATTEMPTS:
                        self._sleep(_retry_delay(response.headers.get('Retry-After'), attempt))
                        continue
                raise error
            finally:
                response.close()

        raise ProviderUnavailableError('Massive is currently unavailable')

    def _wait_for_request_slot(self, api_key: str) -> None:
        schedule_key = self._rate_limit_schedule_key(api_key)
        if self._use_shared_rate_limit and self._wait_for_shared_request_slot(schedule_key):
            return
        self._wait_for_local_request_slot(schedule_key)

    def _wait_for_shared_request_slot(self, schedule_key: str) -> bool:
        state_key = f'massive-rate-limit:{schedule_key}'
        try:
            if sync_redis.get(state_key) is None:
                return False
            while True:
                with sync_redis.lock(f'{state_key}:lock', timeout=10, blocking_timeout=10):
                    raw_state = sync_redis.get(state_key)
                    if raw_state is None:
                        return False
                    interval, next_request_at = _decode_rate_limit_state(raw_state)
                    now = self._wall_time()
                    if next_request_at <= now:
                        sync_redis.set(
                            state_key,
                            json.dumps((interval, now + interval)),
                            ex=MASSIVE_RATE_LIMIT_STATE_TTL_SECONDS,
                        )
                        return True
                    delay = next_request_at - now
                self._sleep(delay)
        except Exception:
            # Redis availability must not prevent historical imports; local pacing remains safe per process.
            return False

    def _wait_for_local_request_slot(self, schedule_key: str) -> None:
        while True:
            now = self._monotonic()
            with _massive_request_schedule_lock:
                state = _massive_request_schedule.get(schedule_key)
                if state is None:
                    return
                interval, next_request_at = state
                if next_request_at <= now:
                    _massive_request_schedule[schedule_key] = (interval, now + interval)
                    return
                delay = next_request_at - now
            self._sleep(delay)

    def _activate_free_tier_pacing(self, api_key: str, retry_after: str | None) -> None:
        now = self._monotonic()
        retry_delay = (
            _retry_delay(retry_after, 0)
            if retry_after is not None
            else MASSIVE_RATE_LIMIT_FALLBACK_SECONDS
        )
        blocked_until = now + max(retry_delay, MASSIVE_FREE_REQUEST_INTERVAL_SECONDS)
        schedule_key = self._rate_limit_schedule_key(api_key)
        with _massive_request_schedule_lock:
            _, next_request_at = _massive_request_schedule.get(schedule_key, (0.0, 0.0))
            _massive_request_schedule[schedule_key] = (
                MASSIVE_FREE_REQUEST_INTERVAL_SECONDS,
                max(next_request_at, blocked_until),
            )
        if not self._use_shared_rate_limit:
            return
        state_key = f'massive-rate-limit:{schedule_key}'
        try:
            shared_blocked_until = self._wall_time() + max(
                retry_delay,
                MASSIVE_FREE_REQUEST_INTERVAL_SECONDS,
            )
            with sync_redis.lock(f'{state_key}:lock', timeout=10, blocking_timeout=10):
                raw_state = sync_redis.get(state_key)
                next_request_at = _decode_rate_limit_state(raw_state)[1] if raw_state is not None else 0.0
                sync_redis.set(
                    state_key,
                    json.dumps((MASSIVE_FREE_REQUEST_INTERVAL_SECONDS, max(next_request_at, shared_blocked_until))),
                    ex=MASSIVE_RATE_LIMIT_STATE_TTL_SECONDS,
                )
        except Exception:
            pass

    def _rate_limit_schedule_key(self, api_key: str) -> str:
        # Only a non-reversible fingerprint enters process state or Redis; the API key never does.
        credential_fingerprint = hashlib.sha256(api_key.encode()).hexdigest()[:16]
        return f'{self.provider_id}:{credential_fingerprint}'

    def _provider_symbol(self, symbol: str, api_key: str) -> str:
        raise NotImplementedError

    def _catalog_entry(self, result: Mapping[str, Any]) -> SymbolCatalogEntry | None:
        raise NotImplementedError


class MassiveStocksProvider(MassiveAggregatesProvider):
    provider_id = exchanges.MASSIVE_STOCKS
    markets = ('stocks',)
    supports_adjustment = True
    capabilities = ProviderCapabilities(
        credential_validation=True,
        ticker_search=True,
        native_timeframes=('1m',),
        adjustment_modes=(AdjustmentMode.SPLIT_ADJUSTED,),
        max_candles_per_request=MASSIVE_PAGE_LIMIT,
        default_adjustment_mode=AdjustmentMode.SPLIT_ADJUSTED,
    )

    def _provider_symbol(self, symbol: str, api_key: str) -> str:
        return _strip_usd_quote(symbol)

    def _catalog_entry(self, result: Mapping[str, Any]) -> SymbolCatalogEntry | None:
        ticker = _catalog_ticker(result)
        if ticker is None or '-' in ticker:
            return None
        type_code = _optional_text(result, 'type')
        return SymbolCatalogEntry(
            f'{ticker}-USD',
            name=_optional_text(result, 'name'),
            kind=MASSIVE_STOCK_TYPE_LABELS.get(type_code.upper(), type_code) if type_code else None,
            venue=_venue_label(_optional_text(result, 'primary_exchange')),
        )


class MassiveCurrenciesProvider(MassiveAggregatesProvider):
    provider_id = exchanges.MASSIVE_CURRENCIES
    markets = ('fx', 'crypto')
    supports_adjustment = True
    capabilities = ProviderCapabilities(
        credential_validation=True,
        ticker_search=True,
        native_timeframes=('1m',),
        max_candles_per_request=MASSIVE_PAGE_LIMIT,
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._resolved_symbols: dict[str, str] = {}

    def _provider_symbol(self, symbol: str, api_key: str) -> str:
        joined_symbol = _joined_pair(symbol)
        cached_symbol = self._resolved_symbols.get(joined_symbol)
        if cached_symbol is not None:
            return cached_symbol
        provider_symbols = set()
        for market, provider_symbol in (('fx', f'C:{joined_symbol}'), ('crypto', f'X:{joined_symbol}')):
            payload = self._request_json(
                MASSIVE_TICKERS_URL,
                api_key,
                {
                    'ticker': provider_symbol,
                    'market': market,
                    'active': 'true',
                    'limit': 1,
                },
            )
            provider_symbols.update(
                ticker
                for result in _ticker_results(payload, (market,))
                if (ticker := _catalog_ticker(result)) == provider_symbol
            )
        if len(provider_symbols) != 1:
            raise ProviderSymbolNotFoundError(
                f'Massive Currencies could not resolve {symbol!r} to one Forex or Crypto ticker'
            )
        provider_symbol = provider_symbols.pop()
        self._resolved_symbols[joined_symbol] = provider_symbol
        return provider_symbol

    def _catalog_entry(self, result: Mapping[str, Any]) -> SymbolCatalogEntry | None:
        market = result.get('market')
        symbol = _catalog_pair(result, 'C:' if market == 'fx' else 'X:')
        if symbol is None:
            return None
        return SymbolCatalogEntry(
            symbol,
            name=_optional_text(result, 'name'),
            kind='Forex' if market == 'fx' else 'Crypto',
        )


class MassiveIndicesProvider(MassiveAggregatesProvider):
    provider_id = exchanges.MASSIVE_INDICES
    markets = ('indices',)
    capabilities = ProviderCapabilities(
        credential_validation=True,
        ticker_search=True,
        native_timeframes=('1m',),
        max_candles_per_request=MASSIVE_PAGE_LIMIT,
    )

    def _provider_symbol(self, symbol: str, api_key: str) -> str:
        return f'I:{_strip_usd_quote(symbol)}'

    def _catalog_entry(self, result: Mapping[str, Any]) -> SymbolCatalogEntry | None:
        ticker = _catalog_ticker(result)
        if ticker is None or not ticker.startswith('I:'):
            return None
        ticker = ticker[2:]
        if not ticker or '-' in ticker:
            return None
        return SymbolCatalogEntry(f'{ticker}-USD', name=_optional_text(result, 'name'), kind='Index')


class MassiveFuturesProvider(MassiveAggregatesProvider):
    """Fetch explicit-expiry futures contracts through Massive's Futures v1 API."""

    provider_id = exchanges.MASSIVE_FUTURES
    capabilities = ProviderCapabilities(
        credential_validation=True,
        ticker_search=True,
        native_timeframes=('1m',),
        max_candles_per_request=MASSIVE_PAGE_LIMIT,
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._resolved_symbols: dict[str, str] = {}

    def _fetch_candles(self, request: HistoricalCandleRequest) -> HistoricalCandleBatch:
        if request.adjustment_mode is not AdjustmentMode.NONE:
            raise HistoricalDataRequestError('Massive Futures requires unadjusted candles')
        api_key = self._credential_loader()
        provider_symbol = self._provider_symbol(request.symbol, api_key)
        url = f'{MASSIVE_FUTURES_AGGREGATES_URL}/{quote(provider_symbol, safe="")}'
        params: dict[str, str | int] | None = {
            'resolution': '1min',
            # Futures v1 accepts nanoseconds and comparison suffixes for an exact half-open range.
            'window_start.gte': request.requested_range.start_timestamp * 1_000_000,
            'window_start.lt': request.requested_range.end_timestamp * 1_000_000,
            'sort': 'window_start.asc',
            'limit': MASSIVE_PAGE_LIMIT,
        }
        candles_by_timestamp: dict[int, HistoricalCandle] = {}
        visited_urls = set()

        for _ in range(MASSIVE_MAX_PAGES):
            if url in visited_urls:
                raise ProviderPaginationError('Massive Futures returned a repeated aggregate pagination URL')
            visited_urls.add(url)
            payload = self._request_json(url, api_key, params)
            for candle in _normalize_futures_page(payload, request, provider_symbol):
                previous = candles_by_timestamp.get(candle.timestamp)
                if previous is not None and previous != candle:
                    raise ProviderPaginationError(
                        f'Massive Futures returned conflicting candles for timestamp {candle.timestamp}'
                    )
                candles_by_timestamp[candle.timestamp] = candle
            next_url = payload.get('next_url')
            if next_url is None:
                return HistoricalCandleBatch(
                    request,
                    tuple(candles_by_timestamp[timestamp] for timestamp in sorted(candles_by_timestamp)),
                )
            url = _validated_next_url(next_url)
            params = None

        raise ProviderPaginationError('Massive Futures aggregate pagination exceeded the safety limit')

    def find_earliest_available_timestamp(self, request: HistoricalCandleRequest) -> int | None:
        """Probe the first entitled aggregate for an explicit futures contract."""
        if request.adjustment_mode is not AdjustmentMode.NONE:
            raise HistoricalDataRequestError('Massive Futures requires unadjusted candles')
        api_key = self._credential_loader()
        provider_symbol = self._provider_symbol(request.symbol, api_key)
        payload = self._request_json(
            f'{MASSIVE_FUTURES_AGGREGATES_URL}/{quote(provider_symbol, safe="")}',
            api_key,
            {
                'resolution': '1min',
                'window_start.gte': request.requested_range.start_timestamp * 1_000_000,
                'window_start.lt': request.requested_range.end_timestamp * 1_000_000,
                'sort': 'window_start.asc',
                'limit': 1,
            },
        )
        candles = _normalize_futures_page(payload, request, provider_symbol)
        return candles[0].timestamp if candles else None

    def search_symbols(self, query: str, limit: int = MASSIVE_TICKER_SEARCH_LIMIT) -> tuple[str, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MASSIVE_TICKER_SEARCH_LIMIT:
            raise HistoricalDataRequestError(
                f'Massive Futures search limit must be between 1 and {MASSIVE_TICKER_SEARCH_LIMIT}'
            )
        normalized_query = query.strip().upper()
        return tuple(
            entry.symbol
            for entry in self.list_symbol_entries()
            if normalized_query in entry.symbol or (entry.name is not None and normalized_query in entry.name.upper())
        )[:limit]

    def list_symbols(self) -> tuple[str, ...]:
        return tuple(entry.symbol for entry in self.list_symbol_entries())

    def list_symbol_entries(self) -> tuple[SymbolCatalogEntry, ...]:
        api_key = self._credential_loader()
        products = self._load_products(api_key)
        url = MASSIVE_FUTURES_CONTRACTS_URL
        params: dict[str, str | int] | None = {
            # A point-in-time snapshot avoids receiving one duplicate per contract per reference date.
            'date': datetime.now(timezone.utc).date().isoformat(),
            'active': 'true',
            'type': 'single',
            'sort': 'ticker.asc',
            'limit': 1_000,
        }
        entries: dict[str, SymbolCatalogEntry] = {}
        visited_urls = set()
        for _ in range(MASSIVE_MAX_PAGES):
            if url in visited_urls:
                raise ProviderPaginationError('Massive Futures returned a repeated contract pagination URL')
            visited_urls.add(url)
            payload = self._request_json(url, api_key, params)
            for entry in _normalize_futures_contracts(payload, products):
                entries.setdefault(entry.symbol, entry)
            next_url = payload.get('next_url')
            if next_url is None:
                if not entries:
                    raise ProviderSchemaError('Massive Futures returned an empty active-contract catalog')
                return tuple(entries.values())
            url = _validated_next_url(next_url)
            params = None
        raise ProviderPaginationError('Massive Futures contract pagination exceeded the safety limit')

    def _load_products(self, api_key: str) -> dict[str, '_FuturesProduct']:
        url = MASSIVE_FUTURES_PRODUCTS_URL
        params: dict[str, str | int] | None = {
            'date': datetime.now(timezone.utc).date().isoformat(),
            'type': 'single',
            # The live API currently accepts name/date sorting even though its docs also list product_code.
            'sort': 'name.asc',
            # The endpoint permits 50,000 products, normally making this a single request.
            'limit': MASSIVE_PAGE_LIMIT,
        }
        products: dict[str, _FuturesProduct] = {}
        visited_urls = set()
        for _ in range(MASSIVE_MAX_PAGES):
            if url in visited_urls:
                raise ProviderPaginationError('Massive Futures returned a repeated product pagination URL')
            visited_urls.add(url)
            payload = self._request_json(url, api_key, params)
            for product in _normalize_futures_products(payload):
                previous = products.get(product.code)
                if previous is not None and previous.currency != product.currency:
                    raise ProviderSchemaError(
                        f'Massive Futures returned conflicting currencies for product {product.code!r}'
                    )
                products.setdefault(product.code, product)
            next_url = payload.get('next_url')
            if next_url is None:
                if not products:
                    raise ProviderSchemaError('Massive Futures returned an empty product catalog')
                return products
            url = _validated_next_url(next_url)
            params = None
        raise ProviderPaginationError('Massive Futures product pagination exceeded the safety limit')

    def _provider_symbol(self, symbol: str, api_key: str) -> str:
        normalized_symbol = symbol.strip().upper()
        cached_symbol = self._resolved_symbols.get(normalized_symbol)
        if cached_symbol is not None:
            return cached_symbol
        provider_symbol, quote_asset = _split_futures_symbol(normalized_symbol)
        contract_payload = self._request_json(
            MASSIVE_FUTURES_CONTRACTS_URL,
            api_key,
            # Without an explicit sort, Massive returns one copy per historical reference date.
            {'ticker': provider_symbol, 'type': 'single', 'sort': 'date.desc', 'limit': 1},
        )
        contracts = [
            result
            for result in _successful_results(contract_payload, 'Futures contract')
            if result.get('ticker') == provider_symbol and result.get('type') in (None, 'single')
        ]
        if len(contracts) != 1:
            raise ProviderSymbolNotFoundError(f'Massive Futures could not resolve contract {provider_symbol!r}')
        product_code = contracts[0].get('product_code')
        if not isinstance(product_code, str) or not product_code.strip():
            raise ProviderSchemaError('Massive Futures contracts require a product_code')
        product_payload = self._request_json(
            MASSIVE_FUTURES_PRODUCTS_URL,
            api_key,
            {'product_code': product_code, 'limit': 2},
        )
        products = _normalize_futures_products(product_payload)
        matching_currencies = {product.currency for product in products if product.code == product_code.upper()}
        if matching_currencies != {quote_asset}:
            raise ProviderSymbolNotFoundError(
                f'Massive Futures contract {provider_symbol!r} does not use currency {quote_asset!r}'
            )
        self._resolved_symbols[normalized_symbol] = provider_symbol
        return provider_symbol

    def _catalog_entry(self, result: Mapping[str, Any]) -> SymbolCatalogEntry | None:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class _FuturesProduct:
    """Product metadata shared by every contract of one Massive futures product code."""

    code: str
    currency: str
    name: str | None = None
    venue: str | None = None


def _optional_text(result: Mapping[str, Any], key: str) -> str | None:
    """Return a stripped string field, treating blanks and non-strings as absent metadata."""
    value = result.get(key)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _venue_label(market_identifier: str | None) -> str | None:
    if market_identifier is None:
        return None
    return MASSIVE_VENUE_LABELS.get(market_identifier.upper(), market_identifier)


def _strip_usd_quote(symbol: str) -> str:
    normalized_symbol = symbol.strip().upper()
    if normalized_symbol.endswith('-USD'):
        normalized_symbol = normalized_symbol[:-4]
    elif '-' in normalized_symbol:
        raise HistoricalDataRequestError('Massive symbols must be direct tickers or use the -USD quote')
    if not normalized_symbol:
        raise HistoricalDataRequestError('Massive ticker must not be empty')
    return normalized_symbol


def _split_futures_symbol(symbol: str) -> tuple[str, str]:
    normalized_symbol = symbol.strip().upper()
    provider_symbol, separator, quote_asset = normalized_symbol.rpartition('-')
    if not separator or not provider_symbol or not quote_asset:
        raise HistoricalDataRequestError('Massive Futures symbols must use the CONTRACT-CURRENCY format')
    return provider_symbol, quote_asset


def _joined_pair(symbol: str) -> str:
    assets = symbol.strip().upper().split('-')
    if len(assets) != 2 or not all(assets):
        raise HistoricalDataRequestError('Massive currency symbols must use the BASE-QUOTE format')
    return ''.join(assets)


def _aggregate_url(provider_symbol: str, request: HistoricalCandleRequest) -> str:
    # Massive's `to` boundary is inclusive; subtracting one millisecond preserves Jesse's half-open range.
    start = request.requested_range.start_timestamp
    end = request.requested_range.end_timestamp - 1
    return f'{MASSIVE_AGGREGATES_URL}/{quote(provider_symbol, safe="")}/range/1/minute/{start}/{end}'


def _validated_next_url(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ProviderPaginationError('Massive returned an invalid pagination URL')
    parsed = urlparse(value)
    if (
        parsed.scheme != 'https'
        or parsed.netloc != MASSIVE_API_HOST
        or not parsed.path.startswith('/')
        or parsed.fragment
    ):
        raise ProviderPaginationError('Massive returned an untrusted pagination URL')
    query_keys = {key.lower() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
    if 'apikey' in query_keys or 'api_key' in query_keys:
        raise ProviderPaginationError('Massive returned credentials in a pagination URL')
    return value


def _response_payload(response: requests.Response) -> Mapping[str, Any]:
    try:
        payload = response.json()
    except requests.exceptions.JSONDecodeError as exc:
        if 200 <= response.status_code < 300:
            raise ProviderSchemaError('Massive returned invalid JSON') from exc
        return {}
    if not isinstance(payload, Mapping):
        if 200 <= response.status_code < 300:
            raise ProviderSchemaError('Massive returned a non-object response')
        return {}
    return payload


def _response_error(status_code: int, payload: Mapping[str, Any]) -> Exception | None:
    if 200 <= status_code < 300:
        return None
    message = _provider_error_message(payload)
    if status_code == 401:
        return ProviderAuthenticationError('Massive rejected the API key')
    if status_code == 403:
        return ProviderEntitlementError('The API key cannot access the requested Massive data')
    if status_code == 404:
        return ProviderSymbolNotFoundError('Massive could not find the requested ticker')
    if status_code == 429:
        if 'quota' in message:
            return ProviderQuotaError('Massive request quota is exhausted')
        return ProviderRateLimitError('Massive rate limit reached')
    if status_code == 400:
        if 'date' in message or 'range' in message or 'timestamp' in message:
            return ProviderRangeError('Massive rejected the requested candle range')
        return ProviderRequestError('Massive rejected the candle request')
    if status_code >= 500:
        return ProviderUnavailableError('Massive is currently unavailable')
    if 300 <= status_code < 400:
        return ProviderPaginationError('Massive attempted an unexpected redirect')
    return ProviderRequestError('Massive could not complete the candle request')


def _provider_error_message(payload: Mapping[str, Any]) -> str:
    for key in ('error', 'message'):
        value = payload.get(key)
        if isinstance(value, str):
            return value.lower()
    return ''


def _normalize_ticker_search(
    payload: Mapping[str, Any],
    expected_markets: tuple[str, ...],
    entry_formatter: Callable[[Mapping[str, Any]], SymbolCatalogEntry | None],
) -> tuple[SymbolCatalogEntry, ...]:
    entries: dict[str, SymbolCatalogEntry] = {}
    for result in _ticker_results(payload, expected_markets):
        entry = entry_formatter(result)
        if entry is not None:
            entries.setdefault(entry.symbol, entry)
    return tuple(entries.values())


def _ticker_results(payload: Mapping[str, Any], expected_markets: tuple[str, ...]) -> tuple[Mapping[str, Any], ...]:
    status = payload.get('status')
    if status is not None and status != 'OK':
        raise ProviderSchemaError('Massive returned an unsuccessful ticker-search payload')
    results = payload.get('results', [])
    if not isinstance(results, list):
        raise ProviderSchemaError('Massive ticker-search results must be an array')
    normalized_results = []
    for result in results:
        if not isinstance(result, Mapping):
            raise ProviderSchemaError('Massive ticker-search entries must be objects')
        # Enforce product boundaries even if a pagination response loses the original market filter.
        if result.get('market') in expected_markets:
            normalized_results.append(result)
    return tuple(normalized_results)


def _catalog_ticker(result: Mapping[str, Any]) -> str | None:
    ticker = result.get('ticker')
    if not isinstance(ticker, str) or not ticker.strip():
        raise ProviderSchemaError('Massive ticker-search entries require a ticker')
    return ticker.strip().upper()


def _catalog_pair(result: Mapping[str, Any], provider_prefix: str) -> str | None:
    ticker = _catalog_ticker(result)
    base = result.get('base_currency_symbol')
    quote_asset = result.get('currency_symbol')
    if not isinstance(base, str) or not isinstance(quote_asset, str):
        return None
    base = base.strip().upper()
    quote_asset = quote_asset.strip().upper()
    if not base or not quote_asset or '-' in base or '-' in quote_asset:
        return None
    if ticker != f'{provider_prefix}{base}{quote_asset}':
        return None
    return f'{base}-{quote_asset}'


def _normalize_page(
    payload: Mapping[str, Any],
    request: HistoricalCandleRequest,
    provider_symbol: str,
    expected_adjusted: bool | None,
) -> tuple[HistoricalCandle, ...]:
    status = payload.get('status')
    if status is not None and status != 'OK':
        raise ProviderSchemaError('Massive returned an unsuccessful payload with a successful HTTP status')
    ticker = payload.get('ticker')
    if ticker is not None and ticker != provider_symbol:
        raise ProviderSchemaError('Massive returned candles for an unexpected ticker')
    adjusted = payload.get('adjusted')
    if expected_adjusted is not None and adjusted is not None and adjusted is not expected_adjusted:
        raise ProviderSchemaError('Massive returned candles with an unexpected adjustment mode')

    results = payload.get('results', [])
    if not isinstance(results, list):
        raise ProviderSchemaError('Massive candle results must be an array')
    try:
        results_count = payload.get('resultsCount')
        if results_count is not None and _strict_int(results_count, 'resultsCount') != len(results):
            raise ProviderSchemaError('Massive resultsCount does not match the returned candles')
        candles_list = []
        for row in results:
            if not isinstance(row, Mapping):
                raise ProviderSchemaError('Massive candle entries must be objects')
            timestamp = _strict_int(row['t'], 'timestamp')
            if not request.requested_range.start_timestamp <= timestamp < request.requested_range.end_timestamp:
                continue
            candles_list.append(
                HistoricalCandle(
                    timestamp=timestamp,
                    open=float(row['o']),
                    high=float(row['h']),
                    low=float(row['l']),
                    close=float(row['c']),
                    # Index values have no volume field; zero records that provider-level absence.
                    volume=float(row.get('v', 0)),
                    vwap=float(row['vw']) if row.get('vw') is not None else None,
                    transaction_count=(
                        _strict_int(row['n'], 'transaction_count') if row.get('n') is not None else None
                    ),
                )
            )
        candles = tuple(candles_list)
    except ProviderSchemaError:
        raise
    except (HistoricalCandleValidationError, KeyError, TypeError, ValueError) as exc:
        raise ProviderSchemaError('Massive returned an invalid candle payload') from exc

    if any(current.timestamp <= previous.timestamp for previous, current in zip(candles, candles[1:])):
        raise ProviderSchemaError('Massive candle timestamps must be ascending and unique within a page')
    return candles


def _normalize_futures_products(payload: Mapping[str, Any]) -> tuple[_FuturesProduct, ...]:
    results = _successful_results(payload, 'Futures product')
    products = []
    for result in results:
        product_code = result.get('product_code')
        currency = result.get('trade_currency_code') or result.get('settlement_currency_code')
        if not isinstance(product_code, str) or not product_code.strip():
            raise ProviderSchemaError('Massive Futures products require a product_code')
        if not isinstance(currency, str) or not currency.strip():
            raise ProviderSchemaError('Massive Futures products require a trade or settlement currency')
        product_code = product_code.strip().upper()
        currency = currency.strip().upper()
        if '-' in product_code or '-' in currency:
            raise ProviderSchemaError('Massive Futures product codes and currencies cannot contain dashes')
        products.append(_FuturesProduct(
            product_code,
            currency,
            _optional_text(result, 'name'),
            _venue_label(_optional_text(result, 'trading_venue')),
        ))
    return tuple(products)


def _normalize_futures_contracts(
    payload: Mapping[str, Any],
    products: Mapping[str, _FuturesProduct],
) -> tuple[SymbolCatalogEntry, ...]:
    results = _successful_results(payload, 'Futures contract')
    entries = []
    for result in results:
        ticker = result.get('ticker')
        product_code = result.get('product_code')
        if not isinstance(ticker, str) or not ticker.strip():
            raise ProviderSchemaError('Massive Futures contracts require a ticker')
        if not isinstance(product_code, str) or not product_code.strip():
            raise ProviderSchemaError('Massive Futures contracts require a product_code')
        if result.get('type') not in (None, 'single'):
            continue
        ticker = ticker.strip().upper()
        product_code = product_code.strip().upper()
        product = products.get(product_code)
        if product is None:
            raise ProviderSchemaError(
                f'Massive Futures contract {ticker!r} references unknown product {product_code!r}'
            )
        if '-' in ticker:
            # Massive occasionally labels calendar spreads as `single`; Jesse imports outright contracts only.
            continue
        entries.append(SymbolCatalogEntry(
            f'{ticker}-{product.currency}',
            # The contract's own name only repeats its ticker; the product name says what is traded.
            name=product.name,
            kind='Future',
            venue=_venue_label(_optional_text(result, 'trading_venue')) or product.venue,
            expiry=_optional_text(result, 'last_trade_date'),
        ))
    return tuple(entries)


def _normalize_futures_page(
    payload: Mapping[str, Any],
    request: HistoricalCandleRequest,
    provider_symbol: str,
) -> tuple[HistoricalCandle, ...]:
    results = _successful_results(payload, 'Futures candle')
    candles = []
    try:
        for result in results:
            ticker = result.get('ticker')
            if ticker is not None and ticker != provider_symbol:
                raise ProviderSchemaError('Massive Futures returned candles for an unexpected ticker')
            timestamp_ns = _strict_int(result['window_start'], 'window_start')
            if timestamp_ns % 1_000_000 != 0:
                raise ProviderSchemaError('Massive Futures window_start must resolve to whole milliseconds')
            timestamp = timestamp_ns // 1_000_000
            if not request.requested_range.start_timestamp <= timestamp < request.requested_range.end_timestamp:
                continue
            volume = float(result['volume'])
            dollar_volume = result.get('dollar_volume')
            candles.append(
                HistoricalCandle(
                    timestamp=timestamp,
                    open=float(result['open']),
                    high=float(result['high']),
                    low=float(result['low']),
                    close=float(result['close']),
                    volume=volume,
                    vwap=float(dollar_volume) / volume if dollar_volume is not None and volume > 0 else None,
                    transaction_count=(
                        _strict_int(result['transactions'], 'transactions')
                        if result.get('transactions') is not None
                        else None
                    ),
                )
            )
    except ProviderSchemaError:
        raise
    except (HistoricalCandleValidationError, KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        raise ProviderSchemaError('Massive Futures returned an invalid candle payload') from exc
    normalized_candles = tuple(candles)
    if any(
        current.timestamp <= previous.timestamp
        for previous, current in zip(normalized_candles, normalized_candles[1:])
    ):
        raise ProviderSchemaError('Massive Futures candle timestamps must be ascending and unique within a page')
    return normalized_candles


def _successful_results(payload: Mapping[str, Any], label: str) -> tuple[Mapping[str, Any], ...]:
    status = payload.get('status')
    if status is not None and status != 'OK':
        raise ProviderSchemaError(f'Massive returned an unsuccessful {label.lower()} payload')
    results = payload.get('results', [])
    if not isinstance(results, list):
        raise ProviderSchemaError(f'Massive {label.lower()} results must be an array')
    if any(not isinstance(result, Mapping) for result in results):
        raise ProviderSchemaError(f'Massive {label.lower()} entries must be objects')
    return tuple(results)


def _strict_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProviderSchemaError(f'Massive {field} must be an integer')
    return value


def _retry_delay(retry_after: str | None, attempt: int) -> float:
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
                delay = 2 ** attempt
        if not isfinite(delay):
            delay = 2 ** attempt
        return min(max(delay, 0.0), MASSIVE_MAX_RETRY_DELAY_SECONDS)
    return float(2 ** attempt)


def _decode_rate_limit_state(value: str | bytes) -> tuple[float, float]:
    decoded_value = value.decode() if isinstance(value, bytes) else value
    state = json.loads(decoded_value)
    if (
        not isinstance(state, list)
        or len(state) != 2
        or any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in state)
    ):
        raise ValueError('Invalid Massive rate-limit state')
    interval, next_request_at = float(state[0]), float(state[1])
    if not isfinite(interval) or interval < 0 or not isfinite(next_request_at):
        raise ValueError('Invalid Massive rate-limit state')
    return interval, next_request_at
