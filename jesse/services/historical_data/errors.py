class HistoricalDataError(Exception):
    code = 'historical_data_error'
    retryable = False


class HistoricalCandleValidationError(HistoricalDataError):
    code = 'invalid_historical_candle'


class HistoricalDataRequestError(HistoricalDataError):
    code = 'invalid_historical_data_request'


class HistoricalDataProviderError(HistoricalDataError):
    code = 'historical_data_provider_error'


class ProviderRequestError(HistoricalDataProviderError):
    code = 'provider_request_invalid'


class ProviderAuthenticationError(HistoricalDataProviderError):
    code = 'provider_authentication_failed'


class ProviderEntitlementError(HistoricalDataProviderError):
    code = 'provider_entitlement_required'


class ProviderRateLimitError(HistoricalDataProviderError):
    code = 'provider_rate_limited'
    retryable = True


class ProviderQuotaError(HistoricalDataProviderError):
    code = 'provider_quota_exhausted'


class ProviderSymbolNotFoundError(HistoricalDataProviderError):
    code = 'provider_symbol_not_found'


class ProviderRangeError(HistoricalDataProviderError):
    code = 'provider_range_invalid'


class ProviderUnavailableError(HistoricalDataProviderError):
    code = 'provider_unavailable'
    retryable = True


class ProviderSchemaError(HistoricalDataProviderError):
    code = 'provider_schema_invalid'


class ProviderPaginationError(HistoricalDataProviderError):
    code = 'provider_pagination_invalid'


class ProviderCapabilityError(HistoricalDataProviderError):
    code = 'provider_capability_unavailable'


class ProviderNotRegisteredError(HistoricalDataProviderError):
    code = 'provider_not_registered'


class ProviderRegistrationError(HistoricalDataProviderError):
    code = 'provider_registration_invalid'


class HistoricalDataImportError(HistoricalDataError):
    code = 'historical_data_import_failed'


class HistoricalDataImportCancelled(HistoricalDataImportError):
    code = 'historical_data_import_cancelled'
