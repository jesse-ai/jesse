from fastapi import APIRouter, Depends
from starlette.responses import JSONResponse

from jesse.services.historical_data.errors import (
    HistoricalDataProviderError,
    ProviderAuthenticationError,
    ProviderEntitlementError,
    ProviderQuotaError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderUnavailableError,
)
from jesse.services import symbol_catalog
from jesse.services.auth import require_auth
from jesse.services.web import (
    DeleteExchangeApiKeyRequestJson,
    ExchangeSupportedSymbolsRequestJson,
    SearchExchangeSymbolsRequestJson,
    StoreExchangeApiKeyRequestJson,
)


router = APIRouter(prefix="/exchange", tags=["Exchange"], dependencies=[Depends(require_auth)])


@router.post('/supported-symbols')
def exchange_supported_symbols(request_json: ExchangeSupportedSymbolsRequestJson) -> JSONResponse:
    
    # if is_dev_env():
    #     return JSONResponse({
    #         'data': [    
    #             'BTC-USDT', 'ETH-USDT', 'SOL-USDT', 'DOGE-USDT'
    #         ]
    #     }, status_code=200)

    return get_exchange_supported_symbols(request_json.exchange)


@router.post('/search-symbols')
def exchange_search_symbols(request_json: SearchExchangeSymbolsRequestJson) -> JSONResponse:
    """Rank one source's symbols for a search term, matching tickers first and provider names second."""
    return search_exchange_symbols(request_json.exchange, request_json.query, request_json.limit)


@router.get('/api-keys')
def get_exchange_api_keys_endpoint() -> JSONResponse:

    from jesse.modes.exchange_api_keys import get_exchange_api_keys
    return get_exchange_api_keys()


@router.post('/api-keys/store')
def store_exchange_api_keys_endpoint(json_request: StoreExchangeApiKeyRequestJson) -> JSONResponse:

    from jesse.modes.exchange_api_keys import store_exchange_api_keys
    return store_exchange_api_keys(
        json_request.exchange, json_request.name, json_request.api_key, json_request.api_secret,
        json_request.additional_fields, json_request.general_notifications_id, json_request.error_notifications_id
    )


@router.post('/api-keys/delete')
def delete_exchange_api_keys_endpoint(json_request: DeleteExchangeApiKeyRequestJson) -> JSONResponse:

    from jesse.modes.exchange_api_keys import delete_exchange_api_keys
    return delete_exchange_api_keys(json_request.id)


def _catalog_error_response(exc: Exception) -> JSONResponse:
    """Map the typed historical-data errors onto the HTTP statuses the Dashboard and MCP expect."""
    if isinstance(exc, symbol_catalog.SymbolCatalogLoadingError):
        return JSONResponse({'error': str(exc)}, status_code=503)
    if isinstance(exc, ProviderAuthenticationError):
        return JSONResponse({'error': str(exc)}, status_code=401)
    if isinstance(exc, ProviderEntitlementError):
        return JSONResponse({'error': str(exc)}, status_code=403)
    if isinstance(exc, (ProviderRateLimitError, ProviderQuotaError)):
        return JSONResponse({'error': str(exc)}, status_code=429)
    if isinstance(exc, ProviderUnavailableError):
        return JSONResponse({'error': str(exc)}, status_code=503)
    if isinstance(exc, (ProviderRequestError, HistoricalDataProviderError)):
        return JSONResponse({'error': str(exc)}, status_code=502)
    return JSONResponse({'error': str(exc)}, status_code=500)


def get_exchange_supported_symbols(exchange: str) -> JSONResponse:
    try:
        catalog = symbol_catalog.load_symbol_catalog(exchange)
    except Exception as exc:
        return _catalog_error_response(exc)
    return JSONResponse(catalog, status_code=200)


def search_exchange_symbols(exchange: str, query: str, limit: int) -> JSONResponse:
    try:
        catalog = symbol_catalog.load_symbol_catalog(exchange)
    except Exception as exc:
        return _catalog_error_response(exc)
    try:
        matches = symbol_catalog.search_symbol_catalog(catalog, query, limit)
    except ValueError as exc:
        return JSONResponse({'error': str(exc)}, status_code=422)
    return JSONResponse({'data': matches, 'catalog_size': len(catalog['data'])}, status_code=200)
