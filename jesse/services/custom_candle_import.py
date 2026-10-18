import codecs
import csv
import math
import re
import sqlite3
import tempfile
from datetime import datetime
from io import TextIOWrapper
from pathlib import Path
from typing import BinaryIO, Callable

from jesse.enums import exchanges
from jesse.models.Candle import Candle
from jesse.repositories.candle_repository import store_observed_candles
from jesse.services.historical_data import HistoricalCandle
from jesse.services.historical_data.errors import HistoricalDataError


REQUIRED_COLUMNS = ('timestamp', 'open', 'close', 'high', 'low', 'volume')
TIMESTAMP_FORMATS = {'auto', 'unix_ms', 'unix_s', 'iso8601'}
SYMBOL_PATTERN = re.compile(r'^[A-Z0-9][A-Z0-9._]*-[A-Z0-9][A-Z0-9._]*$')
# Match the repository insert batch, which remains below PostgreSQL's bind-parameter limit.
IMPORT_BATCH_SIZE = 5_000
# Continue scanning the full upload without returning an unbounded validation payload.
MAX_REPORTED_ERRORS = 20
CLEANING_POLICIES = {'reject', 'drop'}


class CustomCandleImportError(ValueError):
    pass


def normalize_custom_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if not SYMBOL_PATTERN.fullmatch(normalized):
        raise CustomCandleImportError(
            'Symbol must use Jesse pair syntax such as SPY-USD or BTC-USDT.'
        )
    return normalized


def _parse_timestamp(value: str, timestamp_format: str) -> int:
    raw = value.strip()
    selected_format = timestamp_format
    if selected_format == 'auto':
        selected_format = 'unix_ms' if raw.isdigit() and len(raw) >= 12 else 'unix_s' if raw.isdigit() else 'iso8601'

    if selected_format == 'unix_ms':
        timestamp = int(raw)
    elif selected_format == 'unix_s':
        timestamp = int(raw) * 1_000
    else:
        parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise CustomCandleImportError('ISO-8601 timestamps must include a UTC offset or Z suffix.')
        timestamp = int(parsed.timestamp() * 1_000)

    if timestamp < 0 or timestamp % 60_000 != 0:
        raise CustomCandleImportError('Timestamp must be a nonnegative, one-minute-aligned instant.')
    return timestamp


def _parse_candle(row: dict[str, str], timestamp_format: str) -> HistoricalCandle:
    timestamp = _parse_timestamp(row['timestamp'], timestamp_format)
    values = {name: float(row[name]) for name in REQUIRED_COLUMNS[1:]}
    if not all(math.isfinite(value) for value in values.values()):
        raise CustomCandleImportError('OHLCV values must be finite numbers.')
    if min(values['open'], values['high'], values['low'], values['close']) <= 0:
        raise CustomCandleImportError('OHLC prices must be greater than zero.')
    return HistoricalCandle(timestamp=timestamp, **values)


def scan_custom_candle_csv(
    file_object: BinaryIO,
    timestamp_format: str,
    column_mapping: dict[str, str] | None = None,
    consume_batch: Callable[[list[HistoricalCandle]], None] | None = None,
) -> dict:
    """Validate a UTF-8 candle CSV and optionally consume ordered rows in bounded batches."""
    if timestamp_format not in TIMESTAMP_FORMATS:
        raise CustomCandleImportError(f'Unsupported timestamp format: {timestamp_format}')
    mapping = {
        column: (column_mapping or {}).get(column, column).strip().lower()
        for column in REQUIRED_COLUMNS
    }
    if any(not source_column for source_column in mapping.values()):
        raise CustomCandleImportError('Every required candle column must be mapped.')
    if len(set(mapping.values())) != len(mapping):
        raise CustomCandleImportError('Each required candle field must map to a different CSV column.')

    file_object.seek(0)
    # Python 3.10 uploads use SpooledTemporaryFile without TextIOWrapper's readable()
    # interface. The codec reader streams UTF-8/BOM data without owning the binary file.
    text_stream = codecs.getreader('utf-8-sig')(file_object)
    try:
        reader = csv.DictReader(text_stream)
        headers = tuple((header or '').strip().lower() for header in (reader.fieldnames or ()))
        if len(headers) != len(set(headers)):
            raise CustomCandleImportError('CSV column names must be unique.')
        missing_columns = [source_column for source_column in mapping.values() if source_column not in headers]
        if missing_columns:
            raise CustomCandleImportError(f'Missing required CSV columns: {", ".join(missing_columns)}')

        row_count = 0
        valid_row_count = 0
        first_timestamp = None
        last_timestamp = None
        previous_timestamp = None
        missing_minutes = 0
        duplicate_count = 0
        ordering_failure_count = 0
        timestamp_failure_count = 0
        ohlcv_failure_count = 0
        errors = []
        batch: list[HistoricalCandle] = []
        for line_number, raw_row in enumerate(reader, start=2):
            row_count += 1
            source_row = {
                (key or '').strip().lower(): value.strip() if isinstance(value, str) else ''
                for key, value in raw_row.items()
                if key is not None
            }
            row = {column: source_row.get(source_column, '') for column, source_column in mapping.items()}
            try:
                candle = _parse_candle(row, timestamp_format)
                if previous_timestamp is not None:
                    if candle.timestamp == previous_timestamp:
                        raise CustomCandleImportError('Duplicate timestamp; timestamps must be unique.')
                    if candle.timestamp < previous_timestamp:
                        raise CustomCandleImportError('Timestamps must be strictly ascending.')
                    missing_minutes += max(0, (candle.timestamp - previous_timestamp) // 60_000 - 1)
                first_timestamp = candle.timestamp if first_timestamp is None else first_timestamp
                last_timestamp = candle.timestamp
                previous_timestamp = candle.timestamp
                valid_row_count += 1
                batch.append(candle)
                if consume_batch is not None and len(batch) == IMPORT_BATCH_SIZE:
                    consume_batch(batch)
                    batch = []
            except (ValueError, TypeError, KeyError, OverflowError, HistoricalDataError) as exc:
                message = str(exc).lower()
                if 'duplicate timestamp' in message:
                    duplicate_count += 1
                elif 'strictly ascending' in message:
                    ordering_failure_count += 1
                elif 'timestamp' in message or 'iso-8601' in message:
                    timestamp_failure_count += 1
                else:
                    ohlcv_failure_count += 1
                if len(errors) < MAX_REPORTED_ERRORS:
                    errors.append(f'Line {line_number}: {exc}')

        if row_count == 0 and not errors:
            errors.append('The CSV contains no candle rows.')
        if consume_batch is not None and batch and not errors:
            consume_batch(batch)
        return {
            'valid': not errors,
            'row_count': row_count,
            'valid_row_count': valid_row_count,
            'first_timestamp': first_timestamp,
            'last_timestamp': last_timestamp,
            'missing_minutes': missing_minutes,
            'duplicate_count': duplicate_count,
            'ordering_failure_count': ordering_failure_count,
            'timestamp_failure_count': timestamp_failure_count,
            'ohlcv_failure_count': ohlcv_failure_count,
            'errors': errors,
        }
    except UnicodeDecodeError as exc:
        raise CustomCandleImportError('The CSV must be UTF-8 encoded.') from exc
    except csv.Error as exc:
        raise CustomCandleImportError(f'Malformed CSV: {exc}') from exc


def clean_custom_candle_csv(
    file_object: BinaryIO,
    cleaned_file_object: BinaryIO,
    timestamp_format: str,
    column_mapping: dict[str, str],
    invalid_row_policy: str,
) -> dict:
    """Normalize a CSV into canonical timestamp order without inventing or changing candles."""
    if timestamp_format not in TIMESTAMP_FORMATS:
        raise CustomCandleImportError(f'Unsupported timestamp format: {timestamp_format}')
    if invalid_row_policy not in CLEANING_POLICIES:
        raise CustomCandleImportError(f'Unsupported invalid-row policy: {invalid_row_policy}')
    mapping = {
        column: column_mapping.get(column, column).strip().lower()
        for column in REQUIRED_COLUMNS
    }
    if any(not source_column for source_column in mapping.values()):
        raise CustomCandleImportError('Every required candle column must be mapped.')
    if len(set(mapping.values())) != len(mapping):
        raise CustomCandleImportError('Each required candle field must map to a different CSV column.')

    row_count = 0
    invalid_row_count = 0
    duplicate_count = 0
    conflicting_duplicate_count = 0
    ordering_failure_count = 0
    errors = []
    previous_timestamp = None
    file_object.seek(0)
    # Keep upload decoding compatible with Python 3.10's spooled files and leave them open.
    text_stream = codecs.getreader('utf-8-sig')(file_object)
    try:
        reader = csv.DictReader(text_stream)
        headers = tuple((header or '').strip().lower() for header in (reader.fieldnames or ()))
        if len(headers) != len(set(headers)):
            raise CustomCandleImportError('CSV column names must be unique.')
        missing_columns = [source_column for source_column in mapping.values() if source_column not in headers]
        if missing_columns:
            raise CustomCandleImportError(f'Missing required CSV columns: {", ".join(missing_columns)}')

        # A disk-backed primary key keeps sorting and duplicate detection bounded for multi-year files.
        with tempfile.TemporaryDirectory() as temp_directory:
            database_path = Path(temp_directory) / 'custom-candle-cleaning.sqlite3'
            connection = sqlite3.connect(database_path)
            try:
                connection.execute(
                    'CREATE TABLE candles ('
                    'timestamp INTEGER PRIMARY KEY, open REAL, close REAL, high REAL, low REAL, volume REAL'
                    ')'
                )
                for line_number, raw_row in enumerate(reader, start=2):
                    row_count += 1
                    source_row = {
                        (key or '').strip().lower(): value.strip() if isinstance(value, str) else ''
                        for key, value in raw_row.items()
                        if key is not None
                    }
                    row = {column: source_row.get(source_column, '') for column, source_column in mapping.items()}
                    try:
                        candle = _parse_candle(row, timestamp_format)
                    except (ValueError, TypeError, KeyError, OverflowError, HistoricalDataError) as exc:
                        invalid_row_count += 1
                        if len(errors) < MAX_REPORTED_ERRORS:
                            errors.append(f'Line {line_number}: {exc}')
                        continue

                    if previous_timestamp is not None and candle.timestamp < previous_timestamp:
                        ordering_failure_count += 1
                    previous_timestamp = candle.timestamp
                    values = (
                        candle.timestamp,
                        candle.open,
                        candle.close,
                        candle.high,
                        candle.low,
                        candle.volume,
                    )
                    try:
                        connection.execute('INSERT INTO candles VALUES (?, ?, ?, ?, ?, ?)', values)
                    except sqlite3.IntegrityError:
                        stored = connection.execute(
                            'SELECT timestamp, open, close, high, low, volume FROM candles WHERE timestamp = ?',
                            (candle.timestamp,),
                        ).fetchone()
                        if stored == values:
                            duplicate_count += 1
                        else:
                            conflicting_duplicate_count += 1
                            if len(errors) < MAX_REPORTED_ERRORS:
                                errors.append(
                                    f'Line {line_number}: timestamp {candle.timestamp} conflicts with an earlier row.'
                                )
                connection.commit()

                cleaned_row_count = connection.execute('SELECT COUNT(*) FROM candles').fetchone()[0]
                first_timestamp = None
                last_timestamp = None
                missing_minutes = 0
                previous_cleaned_timestamp = None
                cleaned_file_object.seek(0)
                cleaned_file_object.truncate(0)
                cleaned_text_stream = TextIOWrapper(cleaned_file_object, encoding='utf-8', newline='')
                try:
                    writer = csv.writer(cleaned_text_stream, lineterminator='\n')
                    writer.writerow(REQUIRED_COLUMNS)
                    for values in connection.execute(
                        'SELECT timestamp, open, close, high, low, volume FROM candles ORDER BY timestamp'
                    ):
                        timestamp = values[0]
                        first_timestamp = timestamp if first_timestamp is None else first_timestamp
                        last_timestamp = timestamp
                        if previous_cleaned_timestamp is not None:
                            missing_minutes += (timestamp - previous_cleaned_timestamp) // 60_000 - 1
                        previous_cleaned_timestamp = timestamp
                        writer.writerow(values)
                    cleaned_text_stream.flush()
                finally:
                    cleaned_text_stream.detach()
            finally:
                connection.close()
    except UnicodeDecodeError as exc:
        raise CustomCandleImportError('The CSV must be UTF-8 encoded.') from exc
    except csv.Error as exc:
        raise CustomCandleImportError(f'Malformed CSV: {exc}') from exc

    can_import_with_drop = cleaned_row_count > 0 and conflicting_duplicate_count == 0
    can_import_with_reject = can_import_with_drop and invalid_row_count == 0
    return {
        'valid': can_import_with_reject if invalid_row_policy == 'reject' else can_import_with_drop,
        'row_count': row_count,
        'cleaned_row_count': cleaned_row_count,
        'invalid_row_count': invalid_row_count,
        'dropped_row_count': duplicate_count + (invalid_row_count if invalid_row_policy == 'drop' else 0),
        'duplicate_count': duplicate_count,
        'conflicting_duplicate_count': conflicting_duplicate_count,
        'ordering_failure_count': ordering_failure_count,
        'first_timestamp': first_timestamp,
        'last_timestamp': last_timestamp,
        'missing_minutes': missing_minutes,
        'can_import_with_reject': can_import_with_reject,
        'can_import_with_drop': can_import_with_drop,
        'errors': errors,
    }


def import_custom_candle_csv(
    file_object: BinaryIO,
    symbol: str,
    timestamp_format: str,
    column_mapping: dict[str, str],
) -> dict:
    """Validate the complete upload, then persist it atomically as observed custom candles."""
    normalized_symbol = normalize_custom_symbol(symbol)
    report = scan_custom_candle_csv(file_object, timestamp_format, column_mapping)
    if not report['valid']:
        raise CustomCandleImportError(report['errors'][0])

    with Candle._meta.database.atomic():
        persisted_report = scan_custom_candle_csv(
            file_object,
            timestamp_format,
            column_mapping,
            consume_batch=lambda batch: store_observed_candles(
                exchanges.CUSTOM_DATA,
                normalized_symbol,
                '1m',
                batch,
            ),
        )
        if not persisted_report['valid']:
            raise CustomCandleImportError(persisted_report['errors'][0])
    return {
        **report,
        'symbol': normalized_symbol,
        'exchange': exchanges.CUSTOM_DATA,
        'timeframe': '1m',
    }
