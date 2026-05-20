"""
Jesse Backtest Service Functions

This module contains the core backtest service functions used by Jesse's
MCP tools. These functions handle the actual API calls to Jesse's backtest
endpoints.

The functions are separated from the MCP tool wrappers to allow for better
code organization and reusability.
"""

import json
import uuid
import requests
from hashlib import sha256
import jesse.mcp.mcp_config as mcp_config
from jesse.services.web import (
    BacktestRequestJson,
    CancelRequestJson,
    GetBacktestSessionsRequestJson,
    UpdateBacktestSessionStateRequestJson
)
from pydantic import ValidationError
from .auth import hash_password


def create_backtest_draft_service(
    exchange: str = "Binance Perpetual Futures",
    routes: str = '[{"exchange": "Binance Perpetual Futures", "strategy": "ExampleStrategy", "symbol": "BTC-USDT", "timeframe": "4h"}]',
    data_routes: str = '[]',
    start_date: str = "2024-01-01",
    finish_date: str = "2024-03-01",
    debug_mode: bool = False,
    export_csv: bool = False,
    export_json: bool = False,
    export_chart: bool = True,
    export_tradingview: bool = False,
    fast_mode: bool = False,
    benchmark: bool = True
) -> dict:
    """
    Create a new backtest draft with specified configuration.

    This creates a new backtest session with the provided parameters.
    Use update_backtest_draft for modifying existing sessions.

    Args:
        exchange: Exchange name (default: "Binance Perpetual Futures")
        routes: JSON string array of route objects
        data_routes: JSON string array of data route objects
        start_date: Start date in YYYY-MM-DD format
        finish_date: Finish date in YYYY-MM-DD format
        debug_mode: Enable debug mode logging
        export_csv: Export results as CSV
        export_json: Export results as JSON
        export_chart: Export chart data
        export_tradingview: Export TradingView pine script
        fast_mode: Enable fast mode
        benchmark: Run benchmark comparison

    Returns:
        Success confirmation with new session ID
    """
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    try:
        auth_token_hashed = hash_password(password)

        # Generate a unique ID
        backtest_id = str(uuid.uuid4())

        # Parse routes and data_routes
        try:
            routes_list = json.loads(routes)
            data_routes_list = json.loads(data_routes)
        except json.JSONDecodeError as e:
            return {
                'status': 'error',
                'message': 'Invalid JSON format for routes or data_routes',
                'details': str(e)
            }

        # Set selectedRoute to first route (primary route for UI display)
        # Jesse runs all routes in a single session, selectedRoute shows which one is active for display
        # we update the results/selecttedRoute with this object
        if routes_list and len(routes_list) > 0:
            first_route = routes_list[0]
            selected_route = {
                'symbol': first_route.get('symbol', 'BTC-USDT'),
                'timeframe': first_route.get('timeframe', '4h'),
                'strategy': first_route.get('strategy', 'ExampleStrategy')
            }
        else:
            # Fallback to defaults if no routes provided
            selected_route = {"symbol": "BTC-USDT", "timeframe": "4h", "strategy": "ExampleStrategy"}

        # Create complete state structure
        state_dict = {
            'form': {
                'exchange': exchange,
                'routes': routes_list,
                'data_routes': data_routes_list,
                'start_date': start_date,
                'finish_date': finish_date,
                'debug_mode': debug_mode,
                'export_csv': export_csv,
                'export_json': export_json,
                'export_chart': export_chart,
                'export_tradingview': export_tradingview,
                'fast_mode': fast_mode,
                'benchmark': benchmark
            },
            'results': {
                'showResults': False,
                'executing': False,
                'logsModal': False,
                'progressbar': {'current': 0, 'estimated_remaining_seconds': 0},
                'routes_info': [],
                'metrics': {},
                'hyperparameters': [],
                'generalInfo': {'title': None, 'description': None},
                'infoLogs': '',
                'exception': {'error': '', 'traceback': ''},
                'charts': {'equity_curve': []},
                'selectedRoute': selected_route,
                'alert': {'message': '', 'type': ''},
                'info': [],
                'trades': []
            }
        }

        # Store the draft in the session state
        response = requests.post(
            f'{api_url}/backtest/update-state',
            json={
                'id': backtest_id,
                'state': state_dict
            },
            headers={'Authorization': auth_token_hashed},
            timeout=10
        )

        if response.status_code in [200, 404]:
            # 404 is OK - session doesn't exist yet, will be created when run
            return {
                'status': 'success',
                'backtest_id': backtest_id,
                'draft_state': state_dict,
                'message': f'Backtest draft created with ID: {backtest_id}'
            }
        elif response.status_code == 401:
            return {
                'status': 'error',
                'message': 'Authentication failed'
            }
        else:
            # Even if state update fails, return the draft state for reference
            return {
                'status': 'success',
                'backtest_id': backtest_id,
                'draft_state': state_dict,
                'message': f'Backtest draft created with ID: {backtest_id} (state not persisted)',
                'warning': 'Could not persist state to database'
            }

    except json.JSONDecodeError as e:
        return {
            'status': 'error',
            'error': 'Invalid JSON format',
            'details': str(e),
            'message': 'Failed to parse backtest configuration JSON'
        }
    except ValueError as e:
        return {
            'status': 'error',
            'message': str(e)
        }
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'message': 'Failed to create backtest draft'
        }


def update_backtest_draft_service(backtest_id: str, state: str) -> dict:
    """
    Update an existing backtest draft configuration with complete state.

    This replaces the entire state of an existing backtest session. For complex updates
    (like adding routes), use get_backtest_session first to retrieve current state,
    perform merging logic, then call this function with the complete new state.

    Args:
        backtest_id: ID of the backtest session to update (required)
        state: JSON string with complete state object containing 'form' and 'results'.
            Should match dashboard state format with complete data.

    Returns:
        Success confirmation with updated configuration
    """
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    try:
        auth_token_hashed = hash_password(password)

        # Parse the complete state provided by the agent
        state_dict = json.loads(state)

        response = requests.post(
            f'{api_url}/backtest/update-state',
            json={
                'id': backtest_id,
                'state': state_dict
            },
            headers={'Authorization': auth_token_hashed},
            timeout=10
        )

        if response.status_code == 200:
            return {
                'status': 'success',
                'backtest_id': backtest_id,
                'draft_state': state_dict,
                'message': 'Backtest draft updated successfully'
            }
        elif response.status_code == 401:
            return {
                'status': 'error',
                'message': 'Authentication failed'
            }
        else:
            return {
                'status': 'error',
                'message': f'Failed to update backtest draft: {response.text}'
            }

    except json.JSONDecodeError as e:
        return {
            'status': 'error',
            'error': 'Invalid JSON format',
            'details': str(e),
            'message': 'Failed to parse backtest configuration JSON'
        }
    except ValueError as e:
        return {
            'status': 'error',
            'message': str(e)
        }
    except requests.exceptions.RequestException as e:
        return {
            'status': 'error',
            'error': str(e),
            'message': 'Failed to connect to Jesse API'
        }
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'message': 'Failed to update backtest draft'
        }


def get_backtest_session_service(session_id: str) -> dict:
    """
    Get details of a specific backtest session by ID.

    This retrieves a backtest session from the database, including its
    status, configuration, metrics, trades, and other details.

    Args:
        session_id: ID of the backtest session to retrieve

    Returns:
        dict with 'data' and 'error' fields:
        - On success: data contains session info, error is None
        - On error: error contains error message, data is None
    """
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    try:
        auth_token_hashed = hash_password(password)

        # Call the get session endpoint (same as dashboard)
        response = requests.post(
            f'{api_url}/backtest/sessions/{session_id}',
            headers={'Authorization': auth_token_hashed},
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            return {
                'data': {
                    'session': data.get('session', {})
                },
                'error': None,
                'message': 'Backtest session retrieved successfully'
            }
        elif response.status_code == 404:
            return {
                'data': None,
                'error': f'Backtest session {session_id} not found',
                'message': f'Backtest session {session_id} not found'
            }
        elif response.status_code == 401:
            return {
                'data': None,
                'error': 'Authentication failed',
                'message': 'Authentication failed'
            }
        else:
            return {
                'data': None,
                'error': f'Failed to retrieve backtest session: {response.text}',
                'message': f'Failed to retrieve backtest session: {response.text}'
            }

    except ValueError as e:
        return {
            'data': None,
            'error': str(e),
            'message': str(e)
        }
    except requests.exceptions.RequestException as e:
        return {
            'data': None,
            'error': f'Failed to connect to Jesse API: {str(e)}',
            'message': f'Failed to connect to Jesse API: {str(e)}'
        }
    except Exception as e:
        return {
            'data': None,
            'error': f'Failed to retrieve backtest session: {str(e)}',
            'message': f'Failed to retrieve backtest session: {str(e)}'
        }


def get_backtest_sessions_service(
    limit: int = 50,
    offset: int = 0,
    title_search: str = None,
    status_filter: str = None,
    date_filter: str = None
) -> dict:
    """
    List backtest sessions with optional filters and pagination.

    This retrieves a list of backtest sessions from the database, sorted by
    most recently updated.

    Args:
        limit: Maximum number of sessions to return (default: 50)
        offset: Number of sessions to skip for pagination (default: 0)
        title_search: Optional text to search in session titles
        status_filter: Optional status filter (e.g., "finished", "running", "cancelled")
        date_filter: Optional date filter (e.g., "today", "this_week", "this_month")

    Returns:
        List of backtest sessions with their details
    """
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    try:
        auth_token_hashed = hash_password(password)

        # Build request using GetBacktestSessionsRequestJson
        request = GetBacktestSessionsRequestJson(
            limit=limit,
            offset=offset,
            title_search=title_search,
            status_filter=status_filter,
            date_filter=date_filter
        )
        payload = request.model_dump()

        # Call the get sessions endpoint (same as dashboard)
        response = requests.post(
            f'{api_url}/backtest/sessions',
            json=payload,
            headers={'Authorization': auth_token_hashed},
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            return {
                'status': 'success',
                'sessions': data.get('sessions', []),
                'count': data.get('count', 0),
                'message': f'Retrieved {data.get("count", 0)} backtest session(s)'
            }
        elif response.status_code == 401:
            return {
                'status': 'error',
                'message': 'Authentication failed'
            }
        else:
            return {
                'status': 'error',
                'message': f'Failed to retrieve backtest sessions: {response.text}'
            }

    except ValueError as e:
        return {
            'status': 'error',
            'message': str(e)
        }
    except requests.exceptions.RequestException as e:
        return {
            'status': 'error',
            'error': str(e),
            'message': 'Failed to connect to Jesse API'
        }
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'message': 'Failed to retrieve backtest sessions'
        }


def run_backtest_service(session_id: str) -> dict:
    """
    Trigger a backtest and return immediately.

    Fetches the stored session config, merges it with the current backtest config,
    fires POST /backtest, and returns as soon as the server acknowledges (202).
    The caller is responsible for polling get_backtest_session_service(session_id)
    to track progress and retrieve results.

    Args:
        session_id: ID of the backtest session to run

    Returns:
        {"status": "started", "backtest_id": session_id} on success, or an error dict.
    """
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    try:
        auth_token_hashed = hash_password(password)

        # Retrieve the stored session to get form config
        session_response = requests.post(
            f'{api_url}/backtest/sessions/{session_id}',
            headers={'Authorization': auth_token_hashed},
            timeout=10
        )

        if session_response.status_code == 404:
            return {'status': 'error', 'message': f'Backtest session {session_id} not found'}
        elif session_response.status_code == 401:
            return {'status': 'error', 'message': 'Authentication failed'}
        elif session_response.status_code != 200:
            return {'status': 'error', 'message': f'Failed to retrieve session: {session_response.text}'}

        session_data = session_response.json()
        session = session_data.get('session', {})
        state = session.get('state')
        form = state.get('form') if state else None

        if not state or not form:
            return {
                'status': 'error',
                'message': 'No configuration found in session state. Create a draft first using create_backtest_draft.'
            }

        form_data = json.loads(form) if isinstance(form, str) else form

        # Load current backtest config from Jesse
        from .config import get_backtest_config_service
        config_result = get_backtest_config_service()
        if config_result['status'] != 'success':
            return {'status': 'error', 'message': f'Failed to load backtest config: {config_result.get("message", "Unknown error")}'}
        backtest_config = config_result['config']

        backtest_request_dict = {**form_data, 'config': backtest_config, 'id': session_id}

        try:
            backtest_req = BacktestRequestJson(**backtest_request_dict)
            payload = backtest_req.model_dump()
        except ValidationError as e:
            return {'status': 'error', 'message': 'Invalid backtest configuration in session state', 'validation_errors': str(e)}

        # Fire the backtest and return immediately
        response = requests.post(
            f'{api_url}/backtest',
            json=payload,
            headers={'Authorization': auth_token_hashed},
            timeout=10
        )

        if response.status_code == 202:
            return {
                'status': 'started',
                'backtest_id': session_id,
                'message': 'Backtest started. Poll get_backtest_session(session_id) to check progress and retrieve results when status is "finished".'
            }
        elif response.status_code == 401:
            return {'status': 'error', 'message': 'Authentication failed'}
        else:
            return {'status': 'error', 'message': f'Failed to start backtest: {response.text}'}

    except requests.exceptions.RequestException as e:
        return {'status': 'error', 'error': str(e), 'message': 'Failed to connect to Jesse API'}
    except Exception as e:
        return {'status': 'error', 'error': str(e), 'message': 'Failed to run backtest'}


def cancel_backtest_service(session_id: str) -> dict:
    """
    Cancel a running backtest process.

    This cancels a backtest using the same endpoint that the dashboard uses.
    The backtest process will be terminated and its status will be updated
    to 'cancelled' in the database.

    Args:
        session_id: ID of the backtest session to cancel

    Returns:
        Success message or error details
    """
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    try:
        auth_token_hashed = hash_password(password)

        # Create CancelRequestJson
        cancel_request = CancelRequestJson(id=session_id)

        # Call the cancel backtest endpoint (same as dashboard)
        response = requests.post(
            f'{api_url}/backtest/cancel',
            json=cancel_request.model_dump(),
            headers={'Authorization': auth_token_hashed},
            timeout=10
        )

        if response.status_code == 202:
            return {
                'status': 'success',
                'session_id': session_id,
                'message': f'Backtest {session_id} cancellation requested'
            }
        elif response.status_code == 401:
            return {
                'status': 'error',
                'message': 'Authentication failed'
            }
        else:
            return {
                'status': 'error',
                'message': f'Failed to cancel backtest: {response.text}'
            }

    except ValueError as e:
        return {
            'status': 'error',
            'message': str(e)
        }
    except requests.exceptions.RequestException as e:
        return {
            'status': 'error',
            'error': str(e),
            'message': 'Failed to connect to Jesse API'
        }
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'message': 'Failed to cancel backtest'
        }


def purge_backtest_sessions_service(days_old: int = None) -> dict:
    """
    Purge old backtest sessions from the database.

    This deletes backtest sessions using the same endpoint that the dashboard uses.
    If days_old is specified, only sessions older than that many days will be deleted.
    If days_old is None or not specified, all sessions will be deleted.

    Args:
        days_old: Optional number of days. Only sessions older than this will be deleted.
                 If None, all sessions will be purged.

    Returns:
        Number of deleted sessions and success/error message
    """
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    try:
        auth_token_hashed = hash_password(password)

        # Call the purge sessions endpoint (same as dashboard)
        payload = {'days_old': days_old} if days_old is not None else {'days_old': None}

        response = requests.post(
            f'{api_url}/backtest/purge-sessions',
            json=payload,
            headers={'Authorization': auth_token_hashed},
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            deleted_count = data.get('deleted_count', 0)
            return {
                'status': 'success',
                'deleted_count': deleted_count,
                'message': f'Successfully purged {deleted_count} backtest session(s)'
            }
        elif response.status_code == 401:
            return {
                'status': 'error',
                'message': 'Authentication failed'
            }
        else:
            return {
                'status': 'error',
                'message': f'Failed to purge sessions: {response.text}'
            }

    except ValueError as e:
        return {
            'status': 'error',
            'message': str(e)
        }
    except requests.exceptions.RequestException as e:
        return {
            'status': 'error',
            'error': str(e),
            'message': 'Failed to connect to Jesse API'
        }
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'message': 'Failed to purge backtest sessions'
        }