from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from numbers import Real
from collections.abc import Iterator, Mapping
from typing import Any, TypeVar

from jesse.constants import TIMEFRAME_TO_ONE_MINUTES

from .errors import HistoricalCandleValidationError, HistoricalDataRequestError, ProviderCapabilityError


class AssetClass(str, Enum):
    CRYPTO = 'crypto'
    CURRENCY = 'currency'
    EQUITY = 'equity'
    FX = 'fx'
    COMMODITY = 'commodity'
    INDEX = 'index'
    FUTURES = 'futures'


class InstrumentType(str, Enum):
    SPOT = 'spot'
    STOCK = 'stock'
    ETF = 'etf'
    PERPETUAL = 'perpetual'
    FUTURES_CONTRACT = 'futures_contract'
    INDEX = 'index'


class HistoricalDataSourceType(str, Enum):
    PROVIDER = 'provider'
    USER_FILE = 'user_file'


class HistoricalDatasetStatus(str, Enum):
    STAGING = 'staging'
    READY = 'ready'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


class AdjustmentMode(str, Enum):
    NONE = 'none'
    SPLIT_ADJUSTED = 'split_adjusted'


class ImmutableMetadata(Mapping[str, Any]):
    """A recursively immutable, pickle-safe view of JSON-like source metadata."""

    __slots__ = ('_items',)

    def __init__(self, values: Mapping[str, Any] | None = None) -> None:
        items = []
        for key, value in (values or {}).items():
            if not isinstance(key, str):
                raise HistoricalCandleValidationError('source_metadata keys must be strings')
            items.append((key, _freeze_metadata_value(value)))
        self._items = tuple(items)

    def __getitem__(self, key: str) -> Any:
        for item_key, value in self._items:
            if item_key == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (key for key, _ in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __deepcopy__(self, memo: dict[int, Any]) -> 'ImmutableMetadata':
        return self


@dataclass(frozen=True, slots=True)
class HistoricalCandleRange:
    """A half-open UTC millisecond range."""

    start_timestamp: int
    end_timestamp: int

    def __post_init__(self) -> None:
        _validate_timestamp(self.start_timestamp, 'start_timestamp')
        _validate_timestamp(self.end_timestamp, 'end_timestamp')
        if self.start_timestamp >= self.end_timestamp:
            raise HistoricalDataRequestError('start_timestamp must be before end_timestamp')


@dataclass(frozen=True, slots=True)
class HistoricalCandle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float | None = None
    transaction_count: int | None = None

    def __post_init__(self) -> None:
        _validate_timestamp(self.timestamp, 'timestamp')
        for name in ('open', 'high', 'low', 'close', 'volume'):
            _validate_finite_number(getattr(self, name), name)
        if self.vwap is not None:
            _validate_finite_number(self.vwap, 'vwap')
        if self.volume < 0:
            raise HistoricalCandleValidationError('volume must be nonnegative')
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise HistoricalCandleValidationError('open and close must be within low and high')
        if self.high < self.low:
            raise HistoricalCandleValidationError('high must be greater than or equal to low')
        if self.transaction_count is not None:
            if isinstance(self.transaction_count, bool) or not isinstance(self.transaction_count, int):
                raise HistoricalCandleValidationError('transaction_count must be an integer')
            if self.transaction_count < 0:
                raise HistoricalCandleValidationError('transaction_count must be nonnegative')


@dataclass(frozen=True, slots=True)
class SymbolCatalogEntry:
    """One selectable Jesse symbol plus the optional provider metadata that helps a person recognize it."""

    symbol: str
    name: str | None = None
    kind: str | None = None
    venue: str | None = None
    expiry: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise HistoricalCandleValidationError('Symbol catalog entries require a symbol')
        for field_name in ('name', 'kind', 'venue', 'expiry'):
            value = getattr(self, field_name)
            if value is None:
                continue
            if not isinstance(value, str) or not value.strip():
                raise HistoricalCandleValidationError(f'Symbol catalog {field_name} must be a nonempty string')

    def details(self) -> dict[str, str]:
        """Return only the populated descriptive fields so callers never serialize empty metadata."""
        return {
            field_name: value
            for field_name in ('name', 'kind', 'venue', 'expiry')
            if (value := getattr(self, field_name)) is not None
        }


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    credential_validation: bool = False
    ticker_search: bool = False
    native_timeframes: tuple[str, ...] = ('1m',)
    adjustment_modes: tuple[AdjustmentMode, ...] = ()
    max_candles_per_request: int | None = None
    request_delay_seconds: float = 0.0
    default_adjustment_mode: AdjustmentMode = AdjustmentMode.NONE

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            'adjustment_modes',
            tuple(_coerce_enum(AdjustmentMode, value, 'adjustment_mode') for value in self.adjustment_modes),
        )
        object.__setattr__(
            self,
            'default_adjustment_mode',
            _coerce_enum(AdjustmentMode, self.default_adjustment_mode, 'default_adjustment_mode'),
        )
        if not self.native_timeframes:
            raise HistoricalDataRequestError('A candle provider must expose at least one native timeframe')
        unsupported_timeframes = set(self.native_timeframes) - TIMEFRAME_TO_ONE_MINUTES.keys()
        if unsupported_timeframes:
            raise HistoricalDataRequestError(
                f'Unsupported native timeframe: {sorted(unsupported_timeframes)[0]!r}'
            )
        if len(set(self.native_timeframes)) != len(self.native_timeframes):
            raise HistoricalDataRequestError('native_timeframes must be unique')
        if len(set(self.adjustment_modes)) != len(self.adjustment_modes):
            raise HistoricalDataRequestError('adjustment_modes must be unique')
        if (
            self.max_candles_per_request is not None
            and (
                isinstance(self.max_candles_per_request, bool)
                or not isinstance(self.max_candles_per_request, int)
                or self.max_candles_per_request <= 0
            )
        ):
            raise HistoricalDataRequestError('max_candles_per_request must be a positive integer')
        if (
            isinstance(self.request_delay_seconds, bool)
            or not isinstance(self.request_delay_seconds, Real)
            or not isfinite(float(self.request_delay_seconds))
            or self.request_delay_seconds < 0
        ):
            raise HistoricalDataRequestError('request_delay_seconds must be a finite nonnegative number')
        if (
            self.default_adjustment_mode is not AdjustmentMode.NONE
            and self.default_adjustment_mode not in self.adjustment_modes
        ):
            raise HistoricalDataRequestError('default_adjustment_mode must be supported by the provider')


@dataclass(frozen=True, slots=True)
class HistoricalCandleRequest:
    symbol: str
    timeframe: str
    requested_range: HistoricalCandleRange
    adjustment_mode: AdjustmentMode = AdjustmentMode.NONE

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise HistoricalDataRequestError('symbol must not be empty')
        if self.timeframe not in TIMEFRAME_TO_ONE_MINUTES:
            raise HistoricalDataRequestError(f'Unsupported timeframe: {self.timeframe!r}')
        object.__setattr__(
            self,
            'adjustment_mode',
            _coerce_enum(AdjustmentMode, self.adjustment_mode, 'adjustment_mode'),
        )


@dataclass(frozen=True, slots=True)
class HistoricalCandleBatch:
    request: HistoricalCandleRequest
    candles: tuple[HistoricalCandle, ...]
    continuation_token: str | None = None
    next_available_timestamp: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, 'candles', tuple(self.candles))
        interval = TIMEFRAME_TO_ONE_MINUTES[self.request.timeframe] * 60_000
        previous_timestamp: int | None = None
        for candle in self.candles:
            if not isinstance(candle, HistoricalCandle):
                raise HistoricalCandleValidationError('candles must contain HistoricalCandle values')
            if candle.timestamp % interval != 0:
                raise HistoricalCandleValidationError(
                    f'Candle timestamp {candle.timestamp} is not aligned to {self.request.timeframe}'
                )
            if not (
                self.request.requested_range.start_timestamp
                <= candle.timestamp
                < self.request.requested_range.end_timestamp
            ):
                raise HistoricalCandleValidationError('Candle timestamp is outside the requested half-open range')
            if previous_timestamp is not None and candle.timestamp <= previous_timestamp:
                raise HistoricalCandleValidationError('Candle timestamps must be ascending and unique')
            previous_timestamp = candle.timestamp
        if self.continuation_token is not None and not self.continuation_token:
            raise HistoricalDataRequestError('continuation_token must be non-empty when provided')
        if self.next_available_timestamp is not None:
            if self.candles:
                raise HistoricalCandleValidationError(
                    'next_available_timestamp is only valid when the requested range returned no candles'
                )
            _validate_timestamp(self.next_available_timestamp, 'next_available_timestamp')
            if self.next_available_timestamp % interval != 0:
                raise HistoricalCandleValidationError(
                    f'Next available timestamp {self.next_available_timestamp} is not aligned to '
                    f'{self.request.timeframe}'
                )
            if self.next_available_timestamp < self.request.requested_range.end_timestamp:
                raise HistoricalCandleValidationError(
                    'next_available_timestamp must be at or after the requested range'
                )


@dataclass(frozen=True, slots=True)
class HistoricalDataQualitySummary:
    duplicate_count: int = 0
    out_of_order_count: int = 0
    invalid_candle_count: int = 0
    unclassified_gap_count: int = 0

    def __post_init__(self) -> None:
        for name in (
            'duplicate_count',
            'out_of_order_count',
            'invalid_candle_count',
            'unclassified_gap_count',
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise HistoricalCandleValidationError(f'{name} must be a nonnegative integer')


@dataclass(frozen=True, slots=True)
class HistoricalCandleDataset:
    id: str
    source_type: HistoricalDataSourceType
    symbol: str
    source_timeframe: str
    asset_class: AssetClass
    instrument_type: InstrumentType
    requested_range: HistoricalCandleRange
    adjustment_mode: AdjustmentMode
    status: HistoricalDatasetStatus
    row_count: int
    quality: HistoricalDataQualitySummary
    created_at: int
    updated_at: int
    imported_range: HistoricalCandleRange | None = None
    checksum: str | None = None
    provider_id: str | None = None
    display_name: str | None = None
    currency: str | None = None
    timezone: str | None = None
    has_vwap: bool = False
    has_transaction_count: bool = False
    source_metadata: Mapping[str, Any] = field(default_factory=ImmutableMetadata, compare=False, hash=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            'source_type',
            _coerce_enum(HistoricalDataSourceType, self.source_type, 'source_type'),
        )
        object.__setattr__(
            self,
            'asset_class',
            _coerce_enum(AssetClass, self.asset_class, 'asset_class'),
        )
        object.__setattr__(
            self,
            'instrument_type',
            _coerce_enum(InstrumentType, self.instrument_type, 'instrument_type'),
        )
        object.__setattr__(
            self,
            'adjustment_mode',
            _coerce_enum(AdjustmentMode, self.adjustment_mode, 'adjustment_mode'),
        )
        object.__setattr__(
            self,
            'status',
            _coerce_enum(HistoricalDatasetStatus, self.status, 'status'),
        )
        if not isinstance(self.id, str) or not self.id.strip():
            raise HistoricalCandleValidationError('Dataset id must not be empty')
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise HistoricalCandleValidationError('Dataset symbol must not be empty')
        if self.source_timeframe not in TIMEFRAME_TO_ONE_MINUTES:
            raise HistoricalCandleValidationError(f'Unsupported source timeframe: {self.source_timeframe!r}')
        if isinstance(self.row_count, bool) or not isinstance(self.row_count, int) or self.row_count < 0:
            raise HistoricalCandleValidationError('row_count must be a nonnegative integer')
        _validate_timestamp(self.created_at, 'created_at')
        _validate_timestamp(self.updated_at, 'updated_at')
        if self.updated_at < self.created_at:
            raise HistoricalCandleValidationError('updated_at must not be before created_at')
        if self.source_type is HistoricalDataSourceType.PROVIDER and not self.provider_id:
            raise HistoricalCandleValidationError('Provider datasets require provider_id')
        if self.source_type is HistoricalDataSourceType.USER_FILE and self.provider_id is not None:
            raise HistoricalCandleValidationError('User-file datasets cannot declare provider_id')
        if self.status is HistoricalDatasetStatus.READY:
            if self.imported_range is None:
                raise HistoricalCandleValidationError('Ready datasets require imported_range')
            if self.row_count == 0:
                raise HistoricalCandleValidationError('Ready datasets must contain at least one candle')
            if not self.checksum:
                raise HistoricalCandleValidationError('Ready datasets require a checksum')
            if (
                self.imported_range.start_timestamp < self.requested_range.start_timestamp
                or self.imported_range.end_timestamp > self.requested_range.end_timestamp
            ):
                raise HistoricalCandleValidationError('imported_range must be within requested_range')
        object.__setattr__(self, 'source_metadata', ImmutableMetadata(self.source_metadata))


class HistoricalCandleProvider(ABC):
    provider_id: str
    capabilities: ProviderCapabilities

    def fetch_candles(self, request: HistoricalCandleRequest) -> HistoricalCandleBatch:
        """Fetch one normalized page for the explicit half-open request range."""
        if request.timeframe not in self.capabilities.native_timeframes:
            raise HistoricalDataRequestError(
                f'Provider {self.provider_id!r} does not support timeframe {request.timeframe!r}'
            )
        if (
            request.adjustment_mode is not AdjustmentMode.NONE
            and request.adjustment_mode not in self.capabilities.adjustment_modes
        ):
            raise HistoricalDataRequestError(
                f'Provider {self.provider_id!r} does not support adjustment mode '
                f'{request.adjustment_mode.value!r}'
            )
        batch = self._fetch_candles(request)
        if batch.request != request:
            raise HistoricalCandleValidationError('Provider batch request must match the submitted request')
        return batch

    def search_symbols(self, query: str, limit: int = 50) -> tuple[str, ...]:
        """Search provider symbols when the provider advertises ticker-search support."""
        raise ProviderCapabilityError(f'Provider {self.provider_id!r} does not support ticker search')

    def list_symbols(self) -> tuple[str, ...]:
        """List provider symbols when the provider advertises ticker-search support."""
        raise ProviderCapabilityError(f'Provider {self.provider_id!r} does not support symbol discovery')

    def list_symbol_entries(self) -> tuple[SymbolCatalogEntry, ...]:
        """List symbols with descriptive metadata; providers without metadata expose bare symbols."""
        return tuple(SymbolCatalogEntry(symbol) for symbol in self.list_symbols())

    def find_earliest_available_timestamp(self, request: HistoricalCandleRequest) -> int | None:
        """Return the first available candle in a range, or its start when discovery is unsupported."""
        return request.requested_range.start_timestamp

    @abstractmethod
    def _fetch_candles(self, request: HistoricalCandleRequest) -> HistoricalCandleBatch:
        """Implement provider-specific retrieval and return normalized candles."""


def _validate_timestamp(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HistoricalCandleValidationError(f'{name} must be a nonnegative UTC millisecond integer')


def _validate_finite_number(value: Real, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(float(value)):
        raise HistoricalCandleValidationError(f'{name} must be a finite number')


EnumType = TypeVar('EnumType', bound=Enum)


def _coerce_enum(enum_type: type[EnumType], value: Any, name: str) -> EnumType:
    try:
        return value if isinstance(value, enum_type) else enum_type(value)
    except (TypeError, ValueError) as exc:
        raise HistoricalCandleValidationError(f'Unsupported {name}: {value!r}') from exc


def _freeze_metadata_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, str, int, float)):
        return value
    if isinstance(value, Mapping):
        return ImmutableMetadata(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_metadata_value(item) for item in value)
    raise HistoricalCandleValidationError(
        f'source_metadata values must be JSON-like, got {type(value).__name__}'
    )
