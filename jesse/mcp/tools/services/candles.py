"""
Jesse Candles Service Functions

This module contains the core candle service functions used by Jesse's
MCP tools. These functions handle candle data import, management, and retrieval.

The functions are separated from the MCP tool wrappers to allow for better
code organization and reusability.

Where files live: the MCP worker runs on the Jesse host with the project root as its working
directory. `file_path` arguments name files on that host (useful only when the assistant runs
there too); `project_path` arguments name files inside the project's strategies/ or
research_scripts/ folders, resolved with the project file tools' symlink-refusing confinement,
which is how a remote assistant exchanges CSV files with Jesse.
"""

import os
import requests
import uuid
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryFile
from typing import BinaryIO, Literal, Optional
from .auth import hash_password
import jesse.mcp.mcp_config as mcp_config
from jesse.info import backtesting_exchanges, jesse_supported_timeframes, live_trading_exchanges
from jesse.modes.import_candles_mode.drivers import historical_provider_names
from jesse.services import project_files
from jesse.services.custom_candle_import import CustomCandleImportError, clean_custom_candle_csv


# Multi-year CSV validation can outlast ordinary MCP reads, but remains bounded for a stalled backend.
CUSTOM_CSV_REQUEST_TIMEOUT_SECONDS = 300
# An export streams a whole one-minute series from the database to disk; a decade of minutes is
# about five million rows, so this matches copy_candles' generous bound.
EXPORT_REQUEST_TIMEOUT_SECONDS = 600
# One row per stored exchange/symbol pair. A few hundred rows keep the listing useful in an
# assistant's context; narrow with the filters or page with offset instead of raising this.
DEFAULT_CANDLE_SETS_LIMIT = 200
MAX_CANDLE_SETS_LIMIT = 1000
# get_candles returns the live chart's window (warm-up candles ending now). Each candle is about
# 100 bytes of JSON, so 1,000 keeps a result near 100 KB whatever the warm-up setting is.
DEFAULT_CHART_CANDLES_LIMIT = 300
MAX_CHART_CANDLES_LIMIT = 1000
# The dashboard's purge offers the exchanges present in storage; far fewer than this exist.
MAX_PURGE_EXCHANGES = 100
AVAILABILITY_FILTERS = ('all', 'backtesting', 'live')
CUSTOM_DATA_EXCHANGE = 'Custom Data'


def _custom_csv_path(file_path: str) -> Path:
    path = Path(file_path).expanduser()
    if not path.is_absolute():
        raise ValueError('file_path must be an absolute path')
    path = path.resolve(strict=True)
    if not path.is_file() or path.suffix.lower() != '.csv':
        raise ValueError('file_path must point to a CSV file')
    return path


def _open_custom_csv(file_path: Optional[str], project_path: Optional[str]) -> tuple[BinaryIO, dict]:
    """
    Open the CSV named by exactly one of `file_path` (an absolute path on the Jesse host) or
    `project_path` (a project-relative path under strategies/ or research_scripts/) and return
    the open binary file with a description of where it was read from.

    A project path goes through the project file tools' resolver, so it stays inside strategies/
    or research_scripts/ and no symlink is followed. A file_path is the older host-path option
    and is not confined: any readable .csv on the Jesse host can be named (only a cleaning report
    and the imported candles come back).
    """
    has_file = bool(file_path and str(file_path).strip())
    has_project = bool(project_path and str(project_path).strip())
    if has_file == has_project:
        raise ValueError(
            'Pass exactly one of project_path (a CSV inside the Jesse project, e.g. '
            '"research_scripts/data/spy.csv") or file_path (an absolute path on the Jesse host).'
        )
    if has_file:
        path = _custom_csv_path(str(file_path))
        return path.open('rb'), {'file_path': str(path)}

    parts = project_files.parse_path(str(project_path))
    if not parts[-1].lower().endswith('.csv'):
        raise ValueError('project_path must point to a .csv file')
    return os.fdopen(project_files.open_regular_file(parts), 'rb'), {
        'project_path': project_files.display_path(parts),
    }


def _source_error(action: str, exc: Exception) -> dict:
    """Map a refused project path or an unusable CSV source to the tool's error shape."""
    if isinstance(exc, project_files.ProjectFileError):
        return {'status': 'error', 'action': action, 'error_type': exc.error_type, 'message': exc.message}
    return {'status': 'error', 'action': action, 'error_type': 'validation_error', 'message': str(exc)}


def _utc_date(timestamp: Optional[int]) -> Optional[str]:
    if not isinstance(timestamp, int) or isinstance(timestamp, bool):
        return None
    return datetime.fromtimestamp(timestamp / 1000, timezone.utc).strftime('%Y-%m-%d %H:%M')


def _error_detail(response) -> str:
    """Jesse's own error text for a failed candle request, falling back to the raw body."""
    try:
        payload = response.json()
    except ValueError:
        return response.text
    if isinstance(payload, dict):
        return payload.get('error') or payload.get('message') or response.text
    return response.text


def _custom_csv_form(symbol: str) -> dict[str, str]:
    return {
        'symbol': symbol,
        'timestamp_format': 'unix_ms',
        'timestamp_column': 'timestamp',
        'open_column': 'open',
        'close_column': 'close',
        'high_column': 'high',
        'low_column': 'low',
        'volume_column': 'volume',
    }


def _clean_custom_csv(
    file_path: Optional[str],
    project_path: Optional[str],
    timestamp_format: str,
    timestamp_column: str,
    open_column: str,
    close_column: str,
    high_column: str,
    low_column: str,
    volume_column: str,
    invalid_row_policy: Literal['reject', 'drop'],
):
    """Clean the source CSV into a temporary canonical file; returns (file, report, source)."""
    opened, source = _open_custom_csv(file_path, project_path)
    cleaned_file = TemporaryFile(mode='w+b')
    try:
        with opened as source_file:
            report = clean_custom_candle_csv(
                source_file,
                cleaned_file,
                timestamp_format,
                {
                    'timestamp': timestamp_column,
                    'open': open_column,
                    'close': close_column,
                    'high': high_column,
                    'low': low_column,
                    'volume': volume_column,
                },
                invalid_row_policy,
            )
        cleaned_file.seek(0)
        return cleaned_file, report, source
    except Exception:
        cleaned_file.close()
        raise


def preview_custom_candle_csv_service(
    file_path: Optional[str] = None,
    symbol: str = '',
    timestamp_format: str = 'auto',
    timestamp_column: str = 'timestamp',
    open_column: str = 'open',
    close_column: str = 'close',
    high_column: str = 'high',
    low_column: str = 'low',
    volume_column: str = 'volume',
    project_path: Optional[str] = None,
) -> dict:
    """Preview deterministic cleanup and verify the normalized output with Jesse's import API."""
    try:
        cleaned_file, report, source = _clean_custom_csv(
            file_path,
            project_path,
            timestamp_format,
            timestamp_column,
            open_column,
            close_column,
            high_column,
            low_column,
            volume_column,
            'drop',
        )
        try:
            backend_preview = None
            if report['can_import_with_drop']:
                response = requests.post(
                    f'{mcp_config.JESSE_API_URL}/candles/custom/preview',
                    data=_custom_csv_form(symbol),
                    files={'file': ('cleaned-candles.csv', cleaned_file, 'text/csv')},
                    headers={'Authorization': hash_password(mcp_config.JESSE_PASSWORD)},
                    timeout=CUSTOM_CSV_REQUEST_TIMEOUT_SECONDS,
                )
                if response.status_code != 200:
                    return {
                        'status': 'error',
                        'action': 'custom_candle_csv_preview_failed',
                        'error_type': 'api_error',
                        'cleaning_report': report,
                        'message': f'Jesse rejected the normalized CSV: {response.text}',
                    }
                backend_preview = response.json().get('data')
            return {
                'status': 'success',
                'action': 'custom_candle_csv_previewed',
                **source,
                'symbol': symbol.strip().upper(),
                'cleaning_report': report,
                'import_preview': backend_preview,
                'message': (
                    'Preview complete. Choose invalid_row_policy="reject" or "drop" when importing; '
                    'conflicting duplicate timestamps must be fixed in the source file.'
                ),
            }
        finally:
            cleaned_file.close()
    except requests.RequestException as exc:
        # Checked first: requests' exceptions are OSError subclasses.
        return {
            'status': 'error',
            'action': 'custom_candle_csv_preview_failed',
            'error_type': 'network_error',
            'message': f'Could not reach Jesse: {exc}',
        }
    except (CustomCandleImportError, OSError, ValueError, project_files.ProjectFileError) as exc:
        return _source_error('custom_candle_csv_preview_failed', exc)


def clean_and_import_custom_candle_csv_service(
    file_path: Optional[str] = None,
    symbol: str = '',
    invalid_row_policy: Literal['reject', 'drop'] = 'reject',
    timestamp_format: str = 'auto',
    timestamp_column: str = 'timestamp',
    open_column: str = 'open',
    close_column: str = 'close',
    high_column: str = 'high',
    low_column: str = 'low',
    volume_column: str = 'volume',
    project_path: Optional[str] = None,
) -> dict:
    """Clean one CSV and import its canonical rows through Jesse's custom-data endpoint."""
    try:
        cleaned_file, report, source = _clean_custom_csv(
            file_path,
            project_path,
            timestamp_format,
            timestamp_column,
            open_column,
            close_column,
            high_column,
            low_column,
            volume_column,
            invalid_row_policy,
        )
        try:
            if not report['valid']:
                return {
                    'status': 'error',
                    'action': 'custom_candle_csv_import_failed',
                    'error_type': 'validation_error',
                    'cleaning_report': report,
                    'message': (
                        'The selected cleaning policy cannot safely import this file. '
                        'Review invalid rows or conflicting duplicate timestamps.'
                    ),
                }
            response = requests.post(
                f'{mcp_config.JESSE_API_URL}/candles/custom/import',
                data=_custom_csv_form(symbol),
                files={'file': ('cleaned-candles.csv', cleaned_file, 'text/csv')},
                headers={'Authorization': hash_password(mcp_config.JESSE_PASSWORD)},
                timeout=CUSTOM_CSV_REQUEST_TIMEOUT_SECONDS,
            )
            if response.status_code != 201:
                return {
                    'status': 'error',
                    'action': 'custom_candle_csv_import_failed',
                    'error_type': 'api_error',
                    'cleaning_report': report,
                    'message': f'Jesse rejected the normalized CSV: {response.text}',
                }
            imported = response.json().get('data', {})
            return {
                'status': 'success',
                'action': 'custom_candle_csv_imported',
                **source,
                'exchange': imported.get('exchange', CUSTOM_DATA_EXCHANGE),
                'symbol': imported.get('symbol', symbol.strip().upper()),
                'timeframe': '1m',
                'cleaning_report': report,
                'import_report': imported,
                'message': (
                    f'Imported {report["cleaned_row_count"]} cleaned one-minute candles as Custom Data. '
                    'Timestamps that were already stored for this symbol keep their existing values.'
                ),
            }
        finally:
            cleaned_file.close()
    except requests.RequestException as exc:
        # Checked first: requests' exceptions are OSError subclasses.
        return {
            'status': 'error',
            'action': 'custom_candle_csv_import_failed',
            'error_type': 'network_error',
            'message': f'Could not reach Jesse: {exc}',
        }
    except (CustomCandleImportError, OSError, ValueError, project_files.ProjectFileError) as exc:
        return _source_error('custom_candle_csv_import_failed', exc)


def import_candles_service(
    exchange: str,
    symbol: str,
    start_date: str,
    import_id: Optional[str] = None,
) -> dict:
    """
    Trigger a candle import and return immediately.

    Fires POST /candles/import and returns as soon as the server acknowledges (202).
    The caller follows the import with get_candle_import_status_service(import_id).

    Args:
        exchange: Exchange name (e.g., 'Binance Spot', 'Bybit USDT Perpetual')
        symbol: Trading symbol (e.g., 'BTC-USDT', 'ETH-USDT')
        start_date: Start date in YYYY-MM-DD format
        import_id: Optional import ID to reuse for retrying a previous import.
                   If None, a new unique ID is generated.

    Returns:
        {"status": "started", "import_id": "...", ...} on success, or an error dict.
    """
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    try:
        auth_token_hashed = hash_password(password)

        if import_id is None:
            import_id = str(uuid.uuid4())

        response = requests.post(
            f'{api_url}/candles/import',
            json={
                "id": import_id,
                "exchange": exchange,
                "symbol": symbol,
                "start_date": start_date
            },
            headers={'Authorization': auth_token_hashed},
            timeout=30
        )

        if response.status_code == 202:
            return {
                "status": "started",
                "action": "candle_import_started",
                "import_id": import_id,
                "exchange": exchange,
                "symbol": symbol,
                "start_date": start_date,
                "message": f"Candle import started for {symbol} on {exchange}. Poll get_candle_import_status(import_id) until it reaches a terminal state."
            }
        else:
            return {
                "status": "error",
                "action": "candle_import_failed",
                "exchange": exchange,
                "symbol": symbol,
                "import_id": import_id,
                "error_type": "api_error",
                "http_status": response.status_code,
                "message": f"Failed to start candle import: {_error_detail(response)}"
            }

    except Exception as e:
        return {
            "status": "error",
            "action": "candle_import_failed",
            "exchange": exchange,
            "symbol": symbol,
            "error_type": "network_error",
            "message": f"Failed to start candle import: {str(e)}"
        }


def cancel_candle_import_service(
    import_id: str,
) -> dict:
    """
    Cancel an ongoing candle import process.

    Stops the import process for the specified import ID.

    Args:
        import_id: The import process ID to cancel

    Returns:
        Success confirmation or error message
    """
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    try:
        auth_token_hashed = hash_password(password)

        # Make API request to cancel import
        response = requests.post(
            f'{api_url}/candles/cancel-import',
            json={"id": import_id},
            headers={'Authorization': auth_token_hashed},
            timeout=10
        )

        if response.status_code == 202:
            return {
                "status": "success",
                "action": "candle_import_cancelled",
                "import_id": import_id,
                "message": f"Candle import process {import_id} has been requested for termination"
            }
        else:
            return {
                "status": "error",
                "action": "cancel_failed",
                "import_id": import_id,
                "error_type": "api_error",
                "message": f"Failed to cancel import: {response.text}"
            }

    except ValueError as e:
        return {
            "status": "error",
            "action": "config_error",
            "message": str(e)
        }
    except Exception as e:
        return {
            "status": "error",
            "action": "cancel_failed",
            "import_id": import_id,
            "error_type": "network_error",
            "message": f"Network error during cancel: {str(e)}"
        }


def clear_candle_cache_service() -> dict:
    """
    Clear the candles database cache.

    Flushes the cache to ensure fresh data is loaded from the database.

    Returns:
        Success confirmation or error message
    """
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    try:
        auth_token_hashed = hash_password(password)

        # Make API request to clear cache
        response = requests.post(
            f'{api_url}/candles/clear-cache',
            headers={'Authorization': auth_token_hashed},
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            return {
                "status": "success",
                "action": "cache_cleared",
                "message": data.get('message', 'Candles database cache cleared successfully')
            }
        else:
            return {
                "status": "error",
                "action": "cache_clear_failed",
                "error_type": "api_error",
                "message": f"Failed to clear cache: {response.text}"
            }

    except ValueError as e:
        return {
            "status": "error",
            "action": "config_error",
            "message": str(e)
        }
    except Exception as e:
        return {
            "status": "error",
            "action": "cache_clear_failed",
            "error_type": "network_error",
            "message": f"Network error during cache clear: {str(e)}"
        }


def get_candles_service(
    exchange: str,
    symbol: str,
    timeframe: str,
    limit: int = DEFAULT_CHART_CANDLES_LIMIT,
) -> dict:
    """
    Return the stored candles the dashboard's live chart starts from: the live
    `warm_up_candles` setting's number of `timeframe` candles ending now (bigger timeframes are
    built from one-minute rows when the live `generate_candles_from_1m` setting is on). Only the
    newest `limit` of them are returned.

    Args:
        exchange: Exchange name exactly as stored (e.g., 'Binance Perpetual Futures')
        symbol: Trading symbol (e.g., 'BTC-USDT')
        timeframe: One of Jesse's timeframes (e.g., '1m', '5m', '1h', '1D')
        limit: Newest candles to return, 1-MAX_CHART_CANDLES_LIMIT

    Returns:
        Candle window (time in Unix seconds) or error message
    """
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_CHART_CANDLES_LIMIT:
        return {
            "status": "error",
            "action": "candles_retrieval_failed",
            "error_type": "invalid_request",
            "message": f"limit must be between 1 and {MAX_CHART_CANDLES_LIMIT}.",
        }
    if timeframe not in jesse_supported_timeframes:
        return {
            "status": "error",
            "action": "candles_retrieval_failed",
            "error_type": "invalid_request",
            "message": f"timeframe must be one of: {', '.join(jesse_supported_timeframes)}.",
        }

    try:
        auth_token_hashed = hash_password(password)

        # Generate unique request ID
        request_id = str(uuid.uuid4())

        # Make API request to get candles
        response = requests.post(
            f'{api_url}/candles/get',
            json={
                "id": request_id,
                "exchange": exchange,
                "symbol": symbol,
                "timeframe": timeframe
            },
            headers={'Authorization': auth_token_hashed},
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            candles = data.get('data', [])
            total = len(candles)
            returned = candles[-limit:]
            return {
                "status": "success",
                "action": "candles_retrieved",
                "exchange": exchange,
                "symbol": symbol,
                "timeframe": timeframe,
                "window": "live chart warm-up window ending now; candle `time` is Unix seconds",
                "candle_count": len(returned),
                "total_in_window": total,
                "truncated": total > len(returned),
                "candles": returned,
                "message": (
                    f"Returned the newest {len(returned)} of {total} {timeframe} candles for {symbol} on {exchange} "
                    "in the live chart window. For historical coverage use get_existing_candles; for the full "
                    "stored series use export_candles."
                ),
            }
        else:
            return {
                "status": "error",
                "action": "candles_retrieval_failed",
                "exchange": exchange,
                "symbol": symbol,
                "timeframe": timeframe,
                "error_type": "api_error",
                "http_status": response.status_code,
                "message": f"Failed to retrieve candles: {_error_detail(response)}"
            }

    except ValueError as e:
        return {
            "status": "error",
            "action": "config_error",
            "message": str(e)
        }
    except Exception as e:
        return {
            "status": "error",
            "action": "candles_retrieval_failed",
            "exchange": exchange,
            "symbol": symbol,
            "timeframe": timeframe,
            "error_type": "network_error",
            "message": f"Network error during candle retrieval: {str(e)}"
        }


def get_candle_import_status_service(import_id: str) -> dict:
    """
    Check whether a candle import process is still running.

    Single Redis SISMEMBER call on the server — no database queries, no timeout risk.

    Args:
        import_id: The import process ID returned by import_candles()

    Returns:
        {"status": "running"|"finished"|"failed"|"cancelled", "import_id": "...", ...}
    """
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    try:
        auth_token_hashed = hash_password(password)

        response = requests.post(
            f'{api_url}/candles/import-status',
            json={"id": import_id},
            headers={'Authorization': auth_token_hashed},
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            result = {
                "status": data.get("status"),
                "import_id": import_id,
                "message": f"Import {import_id} is {data.get('status')}."
            }
            if data.get('error') is not None:
                result['error'] = data['error']
                result['message'] = f"Import {import_id} failed: {data['error']}"
            if data.get('traceback') is not None:
                result['traceback'] = data['traceback']
            if data.get('result') is not None:
                result['result'] = data['result']
                result['message'] = data['result'].get('message', result['message'])
            # Surface live progress (percent complete, ETA, date reached so far) while
            # the import runs, so the caller sees it advancing instead of a blind "running".
            progress = data.get("progress")
            if progress:
                result["progress"] = progress
                pct = progress.get("current")
                eta = progress.get("estimated_remaining_seconds")
                reached = progress.get("current_date")
                bits = []
                if pct is not None:
                    bits.append(f"{pct}% complete")
                if reached:
                    bits.append(f"reached {reached}")
                if eta is not None:
                    bits.append(f"~{round(eta)}s remaining")
                if bits:
                    result["message"] = f"Import {import_id} is running ({', '.join(bits)})."
            return result
        else:
            return {
                "status": "error",
                "import_id": import_id,
                "error_type": "api_error",
                "message": f"Failed to get import status: {response.text}"
            }

    except Exception as e:
        return {
            "status": "error",
            "import_id": import_id,
            "error_type": "network_error",
            "message": f"Network error checking import status: {str(e)}"
        }


# Listing and deleting scan or remove every row of a series; on a database with years of
# minutes for many symbols that takes far longer than an ordinary read (the dashboard warns it
# can take minutes), so these requests get a generous bound.
LARGE_CANDLE_REQUEST_TIMEOUT_SECONDS = 300


def _existing_filters_error(availability: str, offset: int, limit: int) -> Optional[str]:
    if availability not in AVAILABILITY_FILTERS:
        return f"availability must be one of: {', '.join(AVAILABILITY_FILTERS)}."
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        return 'offset must be 0 or greater.'
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_CANDLE_SETS_LIMIT:
        return f'limit must be between 1 and {MAX_CANDLE_SETS_LIMIT}.'
    return None


def _matches_availability(exchange: str, availability: str) -> bool:
    """The dashboard's "Exchange availability" filter on the Manage Candles page."""
    if availability == 'backtesting':
        return exchange in backtesting_exchanges
    if availability == 'live':
        return exchange in live_trading_exchanges and exchange not in backtesting_exchanges
    return True


def get_existing_candles_service(
    exchange: Optional[str] = None,
    symbol: Optional[str] = None,
    availability: str = 'all',
    offset: int = 0,
    limit: int = DEFAULT_CANDLE_SETS_LIMIT,
) -> dict:
    """
    List stored candles, one entry per exchange and symbol with its first and last stored date.

    The filters are the dashboard's Manage Candles filters: case-insensitive substrings of the
    exchange and symbol, and exchange availability. Results are sorted by exchange and symbol
    and paged with offset/limit.
    """
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    invalid = _existing_filters_error(availability, offset, limit)
    if invalid:
        return {
            "status": "error",
            "action": "existing_candles_retrieval_failed",
            "error_type": "invalid_request",
            "message": invalid,
        }

    try:
        auth_token_hashed = hash_password(password)

        # Make API request to get existing candles
        response = requests.post(
            f'{api_url}/candles/existing',
            headers={'Authorization': auth_token_hashed},
            timeout=LARGE_CANDLE_REQUEST_TIMEOUT_SECONDS,
        )

        if response.status_code == 200:
            data = response.json()
            rows = [row for row in data.get('data', []) if isinstance(row, dict)]
            exchange_filter = (exchange or '').strip().lower()
            symbol_filter = (symbol or '').strip().lower()
            matched = sorted(
                (
                    row for row in rows
                    if exchange_filter in str(row.get('exchange', '')).lower()
                    and symbol_filter in str(row.get('symbol', '')).lower()
                    and _matches_availability(str(row.get('exchange', '')), availability)
                ),
                key=lambda row: (str(row.get('exchange', '')), str(row.get('symbol', ''))),
            )
            page = [
                {
                    'exchange': row.get('exchange'),
                    'symbol': row.get('symbol'),
                    'start_date': row.get('start_date'),
                    'end_date': row.get('end_date'),
                    'backtesting_supported': row.get('exchange') in backtesting_exchanges,
                    # Only import sources can extend a stored series (the dashboard's Update).
                    'updatable': row.get('exchange') in historical_provider_names,
                }
                for row in matched[offset:offset + limit]
            ]
            next_offset = offset + len(page) if offset + len(page) < len(matched) else None
            return {
                "status": "success",
                "action": "existing_candles_retrieved",
                "total_count": len(matched),
                "stored_pairs_count": len(rows),
                "candle_sets_count": len(page),
                "offset": offset,
                "limit": limit,
                "next_offset": next_offset,
                "candle_sets": page,
                "message": (
                    f"Found {len(matched)} stored exchange/symbol pair(s) matching the filters "
                    f"({len(rows)} stored in total); returned {len(page)}."
                ),
            }
        else:
            return {
                "status": "error",
                "action": "existing_candles_retrieval_failed",
                "error_type": "api_error",
                "http_status": response.status_code,
                "message": f"Failed to retrieve existing candles: {_error_detail(response)}"
            }

    except ValueError as e:
        return {
            "status": "error",
            "action": "config_error",
            "message": str(e)
        }
    except Exception as e:
        return {
            "status": "error",
            "action": "existing_candles_retrieval_failed",
            "error_type": "network_error",
            "message": f"Network error during existing candles retrieval: {str(e)}"
        }


def delete_candles_service(
    exchange: str,
    symbol: str,
) -> dict:
    """
    Permanently delete every stored candle (all timeframes) of one exchange/symbol pair, the
    same scope as the dashboard's Delete action on Manage Candles.

    Args:
        exchange: Exchange name exactly as stored (e.g., 'Binance Perpetual Futures')
        symbol: Symbol exactly as stored (e.g., 'BTC-USDT')

    Returns:
        Deleted row count or error message
    """
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    try:
        auth_token_hashed = hash_password(password)

        # Make API request to delete candles
        response = requests.post(
            f'{api_url}/candles/delete',
            json={
                "exchange": exchange,
                "symbol": symbol
            },
            headers={'Authorization': auth_token_hashed},
            timeout=LARGE_CANDLE_REQUEST_TIMEOUT_SECONDS,
        )

        if response.status_code == 200:
            data = response.json()
            deleted_count = data.get('deleted_count')
            if deleted_count == 0:
                message = f'No candles were stored for {symbol} on {exchange}; nothing was deleted.'
            else:
                message = f'Deleted {deleted_count} stored candle rows of {symbol} on {exchange}.'
            return {
                "status": "success",
                "action": "candles_deleted",
                "exchange": exchange,
                "symbol": symbol,
                "deleted_count": deleted_count,
                "message": message,
            }
        else:
            return {
                "status": "error",
                "action": "candles_deletion_failed",
                "exchange": exchange,
                "symbol": symbol,
                "error_type": "api_error",
                "http_status": response.status_code,
                "message": f"Failed to delete candles: {_error_detail(response)}"
            }

    except ValueError as e:
        return {
            "status": "error",
            "action": "config_error",
            "message": str(e)
        }
    except Exception as e:
        return {
            "status": "error",
            "action": "candles_deletion_failed",
            "exchange": exchange,
            "symbol": symbol,
            "error_type": "network_error",
            "message": f"Network error during candle deletion: {str(e)}"
        }


def search_symbols_service(exchange: str, query: str, limit: int = 20) -> dict:
    """
    Search one candle source's symbol catalogue by ticker prefix or provider name.

    Uses the same backend ranking as the Dashboard selectors, so a symbol that can be
    found in the Dashboard can be found here and vice versa.

    Args:
        exchange: Candle source name exactly as Jesse lists it, e.g. "Massive Stocks".
        query: Ticker prefix or part of an instrument name, e.g. "MSFT" or "microsoft".
        limit: Maximum number of matches to return (1-200).

    Returns:
        Ranked matches with any provider details, or an error message.
    """
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    try:
        auth_token_hashed = hash_password(password)
        # Large provider catalogues can take several seconds to load on their first request.
        response = requests.post(
            f'{api_url}/exchange/search-symbols',
            headers={'Authorization': auth_token_hashed},
            json={'exchange': exchange, 'query': query, 'limit': limit},
            timeout=120,
        )

        if response.status_code == 200:
            payload = response.json()
            matches = payload.get('data', [])
            return {
                "status": "success",
                "action": "symbols_searched",
                "exchange": exchange,
                "query": query,
                "match_count": len(matches),
                "catalog_size": payload.get('catalog_size'),
                "matches": matches,
                "message": (
                    f"Found {len(matches)} symbol(s) on {exchange} for {query!r}"
                    if matches else f"No symbol on {exchange} matches {query!r}"
                ),
            }
        try:
            detail = response.json().get('error') or response.text
        except ValueError:
            detail = response.text
        return {
            "status": "error",
            "action": "symbol_search_failed",
            "error_type": "api_error",
            "http_status": response.status_code,
            "message": f"Failed to search symbols on {exchange}: {detail}",
        }
    except ValueError as e:
        return {"status": "error", "action": "config_error", "message": str(e)}
    except Exception as e:
        return {
            "status": "error",
            "action": "symbol_search_failed",
            "error_type": "network_error",
            "message": f"Network error during symbol search: {str(e)}",
        }


def copy_candles_service(
    exchange: str,
    symbol: str,
    target_exchange: str,
    target_symbol: Optional[str] = None,
    delete_source: bool = False,
) -> dict:
    """
    Duplicate stored candles under another exchange (and optionally symbol).

    Lets a backtest select the same data as a different market, e.g. Massive Stocks
    SPY-USD copied to a crypto exchange name so its simulation model applies.

    Returns:
        Copy summary or error message
    """
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    try:
        auth_token_hashed = hash_password(password)
        # Copying a multi-year series row by row can take a while; keep the request bounded but generous.
        response = requests.post(
            f'{api_url}/candles/copy',
            headers={'Authorization': auth_token_hashed},
            json={
                'exchange': exchange,
                'symbol': symbol,
                'target_exchange': target_exchange,
                'target_symbol': target_symbol,
                'delete_source': delete_source,
            },
            timeout=600,
        )

        if response.status_code == 200:
            data = response.json()
            return {
                "status": "success",
                "action": "candles_moved" if delete_source else "candles_copied",
                "source": {"exchange": exchange, "symbol": symbol},
                "target": {"exchange": data.get('target_exchange'), "symbol": data.get('target_symbol')},
                "copied_count": data.get('copied_count'),
                "deleted_count": data.get('deleted_count'),
                "message": data.get('message', 'Candles copied successfully'),
            }
        try:
            detail = response.json().get('error') or response.text
        except ValueError:
            detail = response.text
        return {
            "status": "error",
            "action": "candles_copy_failed",
            "error_type": "api_error",
            "http_status": response.status_code,
            "message": f"Failed to copy candles: {detail}",
        }
    except ValueError as e:
        return {"status": "error", "action": "config_error", "message": str(e)}
    except Exception as e:
        return {
            "status": "error",
            "action": "candles_copy_failed",
            "error_type": "network_error",
            "message": f"Network error during candle copy: {str(e)}",
        }


def purge_candles_service(exchanges: list) -> dict:
    """
    Permanently delete every stored candle of the listed exchanges (all symbols and timeframes),
    the dashboard's "Purge Candles by Exchange" action on Manage Candles.

    Args:
        exchanges: Exchange names exactly as stored, e.g. ["Binance Spot"]

    Returns:
        Deleted row count or error message
    """
    if (
        not isinstance(exchanges, list)
        or not exchanges
        or len(exchanges) > MAX_PURGE_EXCHANGES
        or not all(isinstance(name, str) and name.strip() for name in exchanges)
    ):
        return {
            "status": "error",
            "action": "candles_purge_failed",
            "error_type": "invalid_request",
            "message": (
                f"exchanges must list 1 to {MAX_PURGE_EXCHANGES} exchange names exactly as "
                "get_existing_candles() shows them."
            ),
        }
    names = list(dict.fromkeys(name.strip() for name in exchanges))

    try:
        response = requests.post(
            f'{mcp_config.JESSE_API_URL}/candles/purge',
            json={'exchanges': names},
            headers={'Authorization': hash_password(mcp_config.JESSE_PASSWORD)},
            timeout=LARGE_CANDLE_REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code == 200:
            deleted_count = response.json().get('deleted_count')
            return {
                "status": "success",
                "action": "candles_purged",
                "exchanges": names,
                "deleted_count": deleted_count,
                "message": f"Deleted {deleted_count} stored candle rows of {len(names)} exchange(s): {', '.join(names)}.",
            }
        return {
            "status": "error",
            "action": "candles_purge_failed",
            "exchanges": names,
            "error_type": "api_error",
            "http_status": response.status_code,
            "message": f"Failed to purge candles: {_error_detail(response)}",
        }
    except Exception as e:
        return {
            "status": "error",
            "action": "candles_purge_failed",
            "exchanges": names,
            "error_type": "network_error",
            "message": f"Network error during candle purge: {str(e)}",
        }


def export_candles_service(
    exchange: str,
    symbol: str,
    path: Optional[str] = None,
    overwrite: bool = False,
) -> dict:
    """
    Write one stored one-minute series as CSV into the Jesse project (research_scripts/).

    The file has the dashboard Export's columns and rows, so it can be read back with the
    project file tools, used by research scripts, or re-imported as Custom Data. It is written
    on the Jesse host; nothing is sent to the assistant except the summary.
    """
    try:
        response = requests.post(
            f'{mcp_config.JESSE_API_URL}/candles/export-to-project',
            json={'exchange': exchange, 'symbol': symbol, 'path': path, 'overwrite': bool(overwrite)},
            headers={'Authorization': hash_password(mcp_config.JESSE_PASSWORD)},
            timeout=EXPORT_REQUEST_TIMEOUT_SECONDS,
        )
    except Exception as e:
        return {
            "status": "error",
            "action": "candles_export_failed",
            "exchange": exchange,
            "symbol": symbol,
            "error_type": "network_error",
            "message": f"Network error during candle export: {str(e)}",
        }

    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    if response.status_code != 201:
        return {
            "status": "error",
            "action": "candles_export_failed",
            "exchange": exchange,
            "symbol": symbol,
            "error_type": payload.get('error_type') or 'api_error',
            "http_status": response.status_code,
            "message": f"Failed to export candles: {payload.get('error') or response.text}",
        }

    written_path = payload.get('path')
    return {
        "status": "success",
        "action": "candles_exported",
        "exchange": exchange,
        "symbol": symbol,
        "timeframe": '1m',
        "location": "Jesse project on the Jesse host (not the assistant's machine)",
        "path": written_path,
        "overwritten": payload.get('overwritten'),
        "size_bytes": payload.get('size_bytes'),
        "row_count": payload.get('row_count'),
        "columns": payload.get('columns'),
        "first_timestamp": payload.get('first_timestamp'),
        "last_timestamp": payload.get('last_timestamp'),
        "first_candle_utc": _utc_date(payload.get('first_timestamp')),
        "last_candle_utc": _utc_date(payload.get('last_timestamp')),
        "dashboard_download_page": mcp_config.dashboard_page_url('candles/manage'),
        "message": (
            f"Wrote {payload.get('row_count')} one-minute candles of {symbol} on {exchange} to {written_path} "
            "in the Jesse project. Read it in pages with read_project_file, use it from a research script, "
            "or re-import it with clean_and_import_custom_candle_csv(project_path=...). To download it to "
            "your own computer, use Export on the dashboard's Manage Candles page."
        ),
    }
