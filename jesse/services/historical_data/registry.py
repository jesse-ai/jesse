from collections.abc import Iterator

from .contracts import HistoricalCandleProvider
from .errors import ProviderNotRegisteredError, ProviderRegistrationError


class HistoricalCandleProviderRegistry:
    """Keeps historical data providers separate from live exchange drivers."""

    def __init__(self) -> None:
        self._providers: dict[str, HistoricalCandleProvider] = {}

    def register(self, provider: HistoricalCandleProvider) -> None:
        provider_id = provider.provider_id
        if not isinstance(provider_id, str) or not provider_id or provider_id != provider_id.strip():
            raise ProviderRegistrationError('provider_id must be non-empty and cannot have surrounding whitespace')
        if provider_id in self._providers:
            raise ProviderRegistrationError(f'Historical candle provider {provider_id!r} is already registered')
        self._providers[provider_id] = provider

    def get(self, provider_id: str) -> HistoricalCandleProvider:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise ProviderNotRegisteredError(
                f'Historical candle provider {provider_id!r} is not registered'
            ) from exc

    def ids(self) -> tuple[str, ...]:
        return tuple(self._providers)

    def __iter__(self) -> Iterator[HistoricalCandleProvider]:
        return iter(tuple(self._providers.values()))
