"""
Jesse Candles Service Functions

This module contains the core candle service functions used by Jesse's
MCP tools. These functions handle candle data import, management, and retrieval.

The functions are separated from the MCP tool wrappers to allow for better
code organization and reusability.
"""

import requests
import uuid
import time
from hashlib import sha256
from .auth import hash_password
import jesse.mcp.mcp_config as mcp_config


def _monitor_import_completion(import_id: str, exchange: str, symbol: str, start_date: str, start_time: float) -> dict:
    """
    Monitor an import process until completion using real-time callbacks (dashboard approach).

    Args:
        import_id: The import ID to monitor
        exchange: Exchange name
        symbol: Trading symbol
        start_date: Start date
        start_time: When monitoring started (for duration calculation)

    Returns:
        Completion result dictionary
    """
    from jesse.mcp.ws_listener import register_callback, unregister_callback, is_connected

    # Local state for this monitoring session (dashboard approach: listen and forget globally, but track locally)
    local_state = {
        'progress_count': 0,
        'latest_progress': None,
        'success': False,
        'error': None,
        'exception': None,
    }

    # Track last printed progress to avoid duplicate logs
    last_printed_progress = None

    def event_callback(event: dict):
        """Process events for this specific import_id."""
        # Only process events for our import_id (ID is at root level, not in data)
        if str(event.get('id', '')) != import_id:
            return

        event_type = event.get('event', '')

        # Progress events
        if event_type == 'candles.progressbar':
            local_state['progress_count'] += 1
            local_state['latest_progress'] = event.get('data', {})

        # Success alert
        elif event_type == 'candles.alert' and event.get('data', {}).get('type') == 'success':
            local_state['success'] = True

        # Error alert
        elif event_type == 'candles.alert' and event.get('data', {}).get('type') == 'error':
            local_state['error'] = event.get('data', {})

        # Exception event
        elif event_type == 'candles.exception':
            local_state['exception'] = event.get('data', {})

        # Termination event
        elif event_type == 'candles.termination':
            local_state['exception'] = event.get('data', {})

    # Register callback for real-time events
    register_callback('candles', event_callback)

    try:
        poll_interval = 10  # Check every 10 seconds
        max_monitor_time = 60 * 60  # Maximum 1 hour of monitoring

        print(f"📊 Progress: 0% (starting import for {symbol} on {exchange})")
        last_printed_progress = 0

        while time.time() - start_time < max_monitor_time:
            try:
                if not is_connected():
                    print("⚠️  WebSocket not connected, waiting for connection...")
                    time.sleep(5)
                    continue

                # Check local state (updated in real-time by callback)
                if local_state['success']:
                    duration = int(time.time() - start_time)
                    return {
                        "status": "completed",
                        "action": "candle_import_completed",
                        "import_id": import_id,
                        "exchange": exchange,
                        "symbol": symbol,
                        "start_date": start_date,
                        "duration_seconds": duration,
                        "progress_events_count": local_state['progress_count'],
                        "message": f"Successfully imported {symbol} candles from {exchange} in {duration}s"
                    }

                elif local_state['error'] or local_state['exception']:
                    duration = int(time.time() - start_time)
                    error_details = []
                    if local_state['exception']:
                        error_details.append(str(local_state['exception']))
                    if local_state['error']:
                        error_details.append(str(local_state['error']))

                    return {
                        "status": "failed",
                        "action": "candle_import_failed",
                        "import_id": import_id,
                        "exchange": exchange,
                        "symbol": symbol,
                        "start_date": start_date,
                        "duration_seconds": duration,
                        "error_details": error_details,
                        "progress_events_count": local_state['progress_count'],
                        "message": f"Failed to import {symbol} candles from {exchange} after {duration}s"
                    }

                # Still in progress, show status only when it changes
                if local_state['latest_progress']:
                    progress_pct = local_state['latest_progress'].get('current', 0)
                    # Only print if progress changed
                    if progress_pct != last_printed_progress:
                        print(f"📊 Progress: {progress_pct}%")
                        last_printed_progress = progress_pct

            except Exception as e:
                print(f"⚠️  Error checking progress: {e}")

            time.sleep(poll_interval)

        # Timeout reached
        duration = int(time.time() - start_time)
        return {
            "status": "timeout",
            "action": "candle_import_timeout",
            "import_id": import_id,
            "exchange": exchange,
            "symbol": symbol,
            "start_date": start_date,
            "duration_seconds": duration,
            "message": f"Import monitoring timed out after {duration}s (process may still be running in background)"
        }

    finally:
        # Always unregister callback when done
        unregister_callback('candles', event_callback)


def import_candles_service(
    exchange: str,
    symbol: str,
    start_date: str,
    blocking: bool = True,
    import_id: str = None,
) -> dict:
    """
    Import historical candle data for a specific exchange and symbol.

    Downloads historical candle data from the specified exchange starting from
    the given date. By default, this function blocks and waits for completion.

    Args:
        exchange: Exchange name (e.g., 'binance', 'bybit', 'coinbase')
        symbol: Trading symbol (e.g., 'BTC-USDT', 'ETH-USDT')
        start_date: Start date in YYYY-MM-DD format
        blocking: If True, wait for import completion. If False, return import_id immediately (default: True)
        import_id: Optional import ID to reuse (for retries). If None, generates a new unique ID.

    Returns:
        Success confirmation with import results or error message
    """
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    try:
        auth_token_hashed = hash_password(password)

        # Use provided import_id or generate new one
        if import_id is None:
            import_id = str(uuid.uuid4())
        else:
            # Reusing import_id for retry (dashboard behavior)
            print(f"🔄 Retrying import with existing ID: {import_id}")

        # Make API request to import candles
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
            # Dashboard behavior: Import process started successfully
            # Backend handles all errors and retries internally
            if not blocking:
                return {
                    "status": "success",
                    "action": "candle_import_started",
                    "import_id": import_id,
                    "exchange": exchange,
                    "symbol": symbol,
                    "start_date": start_date,
                    "message": f"Started importing {symbol} candles from {exchange} starting {start_date}. Use get_candle_import_progress with import_id to track progress."
                }

            # Blocking mode: wait for completion
            start_time = time.time()

            return _monitor_import_completion(import_id, exchange, symbol, start_date, start_time)
        else:
            return {
                "status": "error",
                "action": "candle_import_failed",
                "exchange": exchange,
                "symbol": symbol,
                "error_type": "api_error",
                "message": f"Failed to start candle import: {response.text}"
            }

    except ValueError as e:
        return {
            "status": "error",
            "action": "config_error",
            "message": str(e)
        }
    except Exception as e:
        # Initial API call failed - import couldn't start
        return {
            "status": "error",
            "action": "candle_import_failed",
            "exchange": exchange,
            "symbol": symbol,
            "error_type": "network_error",
            "message": f"Failed to start candle import - network error calling Jesse API: {str(e)}"
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
) -> dict:
    """
    Retrieve candle data for analysis.

    Gets historical candle data for the specified exchange, symbol, and timeframe.

    Args:
        exchange: Exchange name (e.g., 'Binance', 'Bybit')
        symbol: Trading symbol (e.g., 'BTC-USDT', 'ETH-USDT')
        timeframe: Timeframe (e.g., '1m', '5m', '1h', '1D', '1W', '1M')

    Returns:
        Candle data or error message
    """
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

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
            return {
                "status": "success",
                "action": "candles_retrieved",
                "exchange": exchange,
                "symbol": symbol,
                "timeframe": timeframe,
                "candle_count": len(candles),
                "candles": candles,
                "message": f"Retrieved {len(candles)} candles for {symbol} on {exchange} ({timeframe})"
            }
        else:
            return {
                "status": "error",
                "action": "candles_retrieval_failed",
                "exchange": exchange,
                "symbol": symbol,
                "timeframe": timeframe,
                "error_type": "api_error",
                "message": f"Failed to retrieve candles: {response.text}"
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


def get_existing_candles_service() -> dict:
    """
    List all imported candle data in the database.

    Returns information about all candles that have been imported and stored.

    Returns:
        List of existing candle data or error message
    """
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    try:
        auth_token_hashed = hash_password(password)

        # Make API request to get existing candles
        response = requests.post(
            f'{api_url}/candles/existing',
            headers={'Authorization': auth_token_hashed},
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            candles_data = data.get('data', [])
            return {
                "status": "success",
                "action": "existing_candles_retrieved",
                "candle_sets_count": len(candles_data),
                "candle_sets": candles_data,
                "message": f"Found {len(candles_data)} candle datasets in database"
            }
        else:
            return {
                "status": "error",
                "action": "existing_candles_retrieval_failed",
                "error_type": "api_error",
                "message": f"Failed to retrieve existing candles: {response.text}"
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
    Remove candle data from the database.

    Permanently deletes candle data for the specified exchange and symbol.

    Args:
        exchange: Exchange name (e.g., 'binance', 'bybit')
        symbol: Trading symbol (e.g., 'BTC-USDT', 'ETH-USDT')

    Returns:
        Success confirmation or error message
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
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            return {
                "status": "success",
                "action": "candles_deleted",
                "exchange": exchange,
                "symbol": symbol,
                "message": data.get('message', f'Candles for {symbol} on {exchange} deleted successfully')
            }
        else:
            return {
                "status": "error",
                "action": "candles_deletion_failed",
                "exchange": exchange,
                "symbol": symbol,
                "error_type": "api_error",
                "message": f"Failed to delete candles: {response.text}"
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