"""
Jesse Candles Service Functions

This module contains the core candle service functions used by Jesse's
MCP tools. These functions handle candle data import, management, and retrieval.

The functions are separated from the MCP tool wrappers to allow for better
code organization and reusability.
"""

import requests
import uuid
from hashlib import sha256
from typing import Optional
from .auth import hash_password
import jesse.mcp.mcp_config as mcp_config


def import_candles_service(
    exchange: str,
    symbol: str,
    start_date: str,
    import_id: Optional[str] = None,
) -> dict:
    """
    Trigger a candle import and return immediately.

    Fires POST /candles/import and returns as soon as the server acknowledges (202).
    The caller is responsible for polling get_existing_candles_service() to confirm
    the data has landed.

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
                "message": f"Candle import started for {symbol} on {exchange}. Poll get_existing_candles() to confirm completion, or cancel_candle_import(import_id) to stop it."
            }
        else:
            return {
                "status": "error",
                "action": "candle_import_failed",
                "exchange": exchange,
                "symbol": symbol,
                "error_type": "api_error",
                "message": f"Failed to start candle import: {response.text}"
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