"""
Shared symbol catalogue loading and search for every historical candle source.

The Dashboard selectors and the MCP tools both consume this module, so a symbol
that can be found in one can be found in the other with the same ranking.
"""

import json
from collections.abc import Iterable, Mapping
from typing import Any


from jesse.enums import exchanges
from jesse.services.historical_data.contracts import SymbolCatalogEntry
from jesse.services.redis import LockError, sync_redis


# The free-tier catalog may cross several one-minute quota windows; the lock expires after ten.
SYMBOL_CATALOG_LOCK_TTL_SECONDS = 600
# Waiting one quota window lets concurrent callers reuse the completed cache without hanging indefinitely.
SYMBOL_CATALOG_LOCK_WAIT_SECONDS = 60
# Provider catalogs change rarely; five minutes keeps repeated selector loads off the provider quota.
SYMBOL_CATALOG_CACHE_TTL_SECONDS = 300
# Versioned once for every historical source because all symbol discovery follows the same contract.
# Version 2 caches descriptive symbol details next to the plain symbol list.
SYMBOL_CATALOG_CACHE_VERSION = 2
SYMBOL_SEARCH_DEFAULT_LIMIT = 50
SYMBOL_SEARCH_MAX_LIMIT = 200


class SymbolCatalogLoadingError(Exception):
    """Another worker is already loading this catalog; the caller should retry shortly."""


def symbol_catalog_payload(entries: Iterable[SymbolCatalogEntry]) -> dict[str, Any]:
    """Shape a provider catalog as the plain symbol list plus details only for symbols that have any."""
    entries = tuple(entries)
    return {
        'data': [entry.symbol for entry in entries],
        'details': {entry.symbol: details for entry in entries if (details := entry.details())},
    }


def _is_string_map(value: object) -> bool:
    return isinstance(value, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in value.items())


def deserialize_symbol_catalog(value: str | bytes) -> dict[str, Any]:
    """Read a cached catalog and reject anything that does not match the versioned shape."""
    catalog = json.loads(value.decode() if isinstance(value, bytes) else value)
    symbols = catalog.get('data') if isinstance(catalog, dict) else None
    details = catalog.get('details') if isinstance(catalog, dict) else None
    if (
        not isinstance(symbols, list)
        or not all(isinstance(symbol, str) for symbol in symbols)
        or not isinstance(details, dict)
        or not all(isinstance(symbol, str) and _is_string_map(symbol_details) for symbol, symbol_details in details.items())
    ):
        raise ValueError('Cached exchange symbol catalog is invalid')
    return {'data': symbols, 'details': details}


def _cache_key(exchange: str) -> str:
    return f'historical-symbols:v{SYMBOL_CATALOG_CACHE_VERSION}:{exchange}'


def load_symbol_catalog(exchange: str) -> dict[str, Any]:
    """
    Return `{'data': [symbols], 'details': {symbol: {...}}}` for one candle source.

    Provider catalogs are cached in Redis and loaded under a shared lock so concurrent
    callers cannot multiply provider requests. Provider failures propagate as the typed
    historical-data errors; a catalog still being loaded elsewhere raises
    SymbolCatalogLoadingError.
    """
    if exchange == exchanges.CUSTOM_DATA:
        from jesse.repositories.candle_repository import get_stored_symbols
        return {'data': get_stored_symbols(exchange), 'details': {}}

    cache_key = _cache_key(exchange)
    cached_result = sync_redis.get(cache_key)
    if cached_result is not None:
        return deserialize_symbol_catalog(cached_result)

    try:
        with sync_redis.lock(
            f'{cache_key}:load-lock',
            timeout=SYMBOL_CATALOG_LOCK_TTL_SECONDS,
            blocking_timeout=SYMBOL_CATALOG_LOCK_WAIT_SECONDS,
        ):
            cached_result = sync_redis.get(cache_key)
            if cached_result is not None:
                return deserialize_symbol_catalog(cached_result)
            # Imported lazily: the driver package pulls in the whole import pipeline.
            from jesse.modes.import_candles_mode.drivers import build_historical_provider_registry
            provider = build_historical_provider_registry((exchange,)).get(exchange)
            catalog = symbol_catalog_payload(provider.list_symbol_entries())
            sync_redis.setex(cache_key, SYMBOL_CATALOG_CACHE_TTL_SECONDS, json.dumps(catalog))
            return catalog
    except LockError as exc:
        raise SymbolCatalogLoadingError('The symbol catalog is still loading') from exc


def search_symbol_catalog(
    catalog: Mapping[str, Any],
    query: str,
    limit: int = SYMBOL_SEARCH_DEFAULT_LIMIT,
) -> list[dict[str, str]]:
    """
    Rank catalog symbols for a search term the same way the Dashboard selectors do.

    Symbol prefixes come first so a typed ticker keeps working, then symbols whose
    provider name contains the term. Each result is `{'symbol': ..., **details}`.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= SYMBOL_SEARCH_MAX_LIMIT:
        raise ValueError(f'limit must be between 1 and {SYMBOL_SEARCH_MAX_LIMIT}')
    normalized_query = query.strip().lower()
    if not normalized_query:
        return []

    symbols: list[str] = catalog.get('data', [])
    details: Mapping[str, Mapping[str, str]] = catalog.get('details', {})
    matches = [symbol for symbol in symbols if symbol.lower().startswith(normalized_query)]
    if len(matches) < limit:
        matched = set(matches)
        for symbol in symbols:
            if len(matches) >= limit:
                break
            if symbol in matched:
                continue
            name = details.get(symbol, {}).get('name')
            if name and normalized_query in name.lower():
                matches.append(symbol)
    return [{'symbol': symbol, **details.get(symbol, {})} for symbol in matches[:limit]]
