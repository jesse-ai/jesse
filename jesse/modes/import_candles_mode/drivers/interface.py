from abc import ABC, abstractmethod
import requests
from jesse import exceptions
from jesse.helpers import timeframe_to_one_minutes
from jesse.services.historical_data import (
    HistoricalCandle,
    HistoricalCandleBatch,
    HistoricalCandleProvider,
    HistoricalCandleRequest,
    ProviderCapabilities,
)
from jesse.services.historical_data.errors import (
    HistoricalDataError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderSchemaError,
    ProviderSymbolNotFoundError,
    ProviderUnavailableError,
)


class CandleExchange(HistoricalCandleProvider, ABC):
    def __init__(self, name: str, count: int, rate_limit_per_second: float, backup_exchange_class):
        self.name = name
        self.provider_id = name
        # Crypto persistence imports native 1m bars and derives larger timeframes later.
        self.capabilities = ProviderCapabilities(
            native_timeframes=('1m',),
            max_candles_per_request=count,
            request_delay_seconds=1 / rate_limit_per_second,
        )
        self.count = count
        self.sleep_time = 1 / rate_limit_per_second
        self._backup_exchange_class = backup_exchange_class
        self._backup_exchange = None

    @property
    def backup_exchange(self):
        if self._backup_exchange_class is None:
            return None

        if self._backup_exchange is None:
            self._backup_exchange = self._backup_exchange_class()

        return self._backup_exchange

    @abstractmethod
    def fetch(self, symbol: str, start_timestamp: int, timeframe: str) -> list:
        pass

    def find_earliest_available_timestamp(self, request: HistoricalCandleRequest) -> int | None:
        """
        Clip the request to the symbol's listing so an early start date does not page through
        years of empty history one request at a time.
        """
        try:
            starting_time = self.get_starting_time(request.symbol)
        except HistoricalDataError:
            raise
        except (exceptions.SymbolNotFound, exceptions.InvalidSymbol) as exc:
            raise ProviderSymbolNotFoundError(str(exc)) from exc
        except exceptions.ExchangeInMaintenance as exc:
            raise ProviderUnavailableError(str(exc)) from exc
        except Exception:
            # A driver without a reliable listing lookup falls back to paging; the page loop
            # still stops as soon as the exchange reports only later candles.
            return request.requested_range.start_timestamp
        if starting_time is None:
            return request.requested_range.start_timestamp
        if starting_time >= request.requested_range.end_timestamp:
            return None
        return max(request.requested_range.start_timestamp, int(starting_time))

    def _fetch_candles(self, request: HistoricalCandleRequest) -> HistoricalCandleBatch:
        """Adapt one legacy provider page to the shared immutable candle contract."""
        interval = timeframe_to_one_minutes(request.timeframe) * 60_000
        # Bound the page geometrically because sparse markets can return short pages and
        # some legacy drivers overfetch beyond their declared page size.
        page_end = min(
            request.requested_range.end_timestamp,
            request.requested_range.start_timestamp + self.count * interval,
        )

        try:
            rows = self.fetch(
                request.symbol,
                request.requested_range.start_timestamp,
                request.timeframe,
            )
        except HistoricalDataError:
            raise
        except (exceptions.SymbolNotFound, exceptions.InvalidSymbol) as exc:
            raise ProviderSymbolNotFoundError(str(exc)) from exc
        except exceptions.ExchangeInMaintenance as exc:
            raise ProviderUnavailableError(str(exc)) from exc
        except (requests.exceptions.ConnectionError, ConnectionError) as exc:
            # Legacy HTTP handling discards status metadata, but retains 429/rate-limit text.
            message = str(exc)
            if '429' in message or 'rate limit' in message.lower():
                raise ProviderRateLimitError(message) from exc
            raise ProviderUnavailableError(message) from exc
        except requests.exceptions.JSONDecodeError as exc:
            raise ProviderSchemaError(str(exc)) from exc
        except ValueError as exc:
            # Legacy 404 handling retains this phrase after discarding the response status.
            if 'check the symbol' in str(exc).lower():
                raise ProviderSymbolNotFoundError(str(exc)) from exc
            raise ProviderRequestError(str(exc)) from exc
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderSchemaError(str(exc)) from exc

        try:
            normalized_rows = tuple((int(row['timestamp']), row) for row in rows)
            candles = tuple(
                HistoricalCandle(
                    timestamp=timestamp,
                    open=float(row['open']),
                    high=float(row['high']),
                    low=float(row['low']),
                    close=float(row['close']),
                    volume=float(row['volume']),
                )
                for timestamp, row in normalized_rows
                if request.requested_range.start_timestamp <= timestamp < page_end
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderSchemaError(f'Invalid candle payload from {self.provider_id}: {exc}') from exc

        continuation_token = str(page_end) if page_end < request.requested_range.end_timestamp else None
        future_timestamps = tuple(timestamp for timestamp, _ in normalized_rows if timestamp >= page_end)
        # Some crypto APIs ignore unavailable old ranges and return their first real later candle.
        next_available_timestamp = min(future_timestamps) if not candles and future_timestamps else None
        return HistoricalCandleBatch(
            request,
            candles,
            continuation_token=continuation_token,
            next_available_timestamp=next_available_timestamp,
        )

    def list_symbols(self) -> tuple[str, ...]:
        """Expose legacy exchange discovery through the shared historical-provider contract."""
        return tuple(self.get_available_symbols())

    @abstractmethod
    def get_starting_time(self, symbol: str) -> int:
        pass

    @abstractmethod
    def get_available_symbols(self) -> list:
        pass

    @staticmethod
    def validate_response(response: requests.Response) -> None:
        if response.status_code == 502:
            raise exceptions.ExchangeInMaintenance('ERROR: 502 Bad Gateway. Please try again later')
        elif response.status_code // 100 == 5:
            raise ConnectionError('ERROR: {} {}'.format(response.status_code, response.reason))

        # unsupported inputs
        if response.status_code == 400:
            raise ValueError(response.content)

        # unsupported inputs
        if response.status_code == 404:
            raise ValueError(f'ERROR {response.status_code} {response.reason}. Check the symbol')

        # 429: request-weight limit hit; 418: the IP kept sending after 429s and is temporarily banned
        # (Binance and Binance-style APIs). Every process on the same IP counts toward the limit.
        if response.status_code in (418, 429):
            retry_after = (getattr(response, 'headers', None) or {}).get('Retry-After')
            wait = f' The exchange asks to wait {retry_after} seconds.' if retry_after else ''
            if response.status_code == 418:
                explanation = ('the exchange has temporarily banned this IP address for sending too many requests '
                               'after rate-limit warnings. The ban lifts on its own.')
            else:
                explanation = 'the request rate limit for this IP address was reached.'
            raise ConnectionError(
                f'ERROR {response.status_code} {response.reason}: {explanation}{wait} Reduce how often this IP '
                f'calls the exchange - other bots or scripts on the same IP count too.'
            )

        # if the response code is not in the 200-299, raise an exception
        if response.status_code // 100 != 2:
            raise ConnectionError(f'ERROR {response.status_code} {response.reason}')
