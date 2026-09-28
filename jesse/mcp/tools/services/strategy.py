"""
Jesse Strategy Service Functions

This module contains the core strategy service functions used by Jesse's
MCP tools. These functions handle the actual API calls to Jesse's strategy
endpoints.

The functions are separated from the MCP tool wrappers to allow for better
code organization and reusability.
"""

import requests

from .auth import hash_password
import jesse.mcp.mcp_config as mcp_config

# Where a saved report lives, spelled out because the assistant may run on another machine.
REPORT_LOCATION = (
    'Saved on the machine running Jesse, inside the Jesse project folder. '
    "It is not in the assistant's local workspace."
)


def create_strategy_service(name: str) -> dict:
    """
    Create a new trading strategy in Jesse.

    Args:
        name: Name of the new strategy to create

    Returns:
        Success or error message
    """
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD
    try:
        auth_token_hashed = hash_password(password)

        # Make authenticated request to create the strategy
        import requests
        response = requests.post(
            f'{api_url}/strategy/make',
            json={'name': name},
            headers={'Authorization': auth_token_hashed},  # Jesse uses token directly, not Bearer format
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                return {
                    "status": "success",
                    "action": "strategy_created",
                    "strategy_name": name,
                    "message": f"Strategy '{name}' created successfully",
                    "path": data.get('message')
                }
            else:
                return {
                    "status": "error",
                    "action": "strategy_creation_failed",
                    "strategy_name": name,
                    "error_type": "api_error",
                    "message": data.get('message', 'Unknown error')
                }
        elif response.status_code == 401:
            return {
                "status": "error",
                "action": "strategy_creation_failed",
                "strategy_name": name,
                "error_type": "authentication_failed",
                "message": "Invalid password provided"
            }
        elif response.status_code == 409:
            return {
                "status": "error",
                "action": "strategy_creation_failed",
                "strategy_name": name,
                "error_type": "strategy_exists",
                "message": f"Strategy '{name}' already exists"
            }
        else:
            return {
                "status": "error",
                "action": "strategy_creation_failed",
                "strategy_name": name,
                "error_type": "http_error",
                "http_status": response.status_code,
                "message": response.text
            }

    except ValueError as e:
        return {
            "status": "error",
            "action": "strategy_creation_failed",
            "strategy_name": name,
            "error_type": "configuration_error",
            "message": str(e)
        }
    except requests.exceptions.RequestException as e:
        return {
            "status": "error",
            "action": "strategy_creation_failed",
            "strategy_name": name,
            "error_type": "connection_error",
            "message": f"Could not connect to Jesse API",
            "details": str(e)
        }


def read_strategy_service(name: str) -> dict:
    """
    Read the content of a trading strategy using Jesse's API.

    Args:
        name: Name of the strategy to read

    Returns:
        Dictionary containing strategy content or error message
    """
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD
    try:
        auth_token_hashed = hash_password(password)

        # Make authenticated request to get the strategy
        import requests
        response = requests.post(
            f'{api_url}/strategy/get',
            json={'name': name},
            headers={'Authorization': auth_token_hashed},  # Jesse uses token directly, not Bearer format
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                return {
                    "status": "success",
                    "action": "strategy_read",
                    "strategy_name": name,
                    "message": f"Strategy '{name}' content read successfully",
                    "content": data.get('content')
                }
            else:
                return {
                    "status": "error",
                    "action": "strategy_read_failed",
                    "strategy_name": name,
                    "error_type": "api_error",
                    "message": data.get('message', 'Unknown error')
                }
        elif response.status_code == 401:
            return {
                "status": "error",
                "action": "strategy_read_failed",
                "strategy_name": name,
                "error_type": "authentication_failed",
                "message": "Invalid password provided"
            }
        elif response.status_code == 404:
            return {
                "status": "error",
                "action": "strategy_read_failed",
                "strategy_name": name,
                "error_type": "strategy_not_found",
                "message": f"Strategy '{name}' not found"
            }
        else:
            return {
                "status": "error",
                "action": "strategy_read_failed",
                "strategy_name": name,
                "error_type": "http_error",
                "http_status": response.status_code,
                "message": response.text
            }

    except ValueError as e:
        return {
            "status": "error",
            "action": "strategy_read_failed",
            "strategy_name": name,
            "error_type": "configuration_error",
            "message": str(e)
        }
    except requests.exceptions.RequestException as e:
        return {
            "status": "error",
            "action": "strategy_read_failed",
            "strategy_name": name,
            "error_type": "connection_error",
            "message": f"Could not connect to Jesse API",
            "details": str(e)
        }


def write_strategy_service(name: str, content: str) -> dict:
    """
    Write content to a trading strategy using Jesse's API.

    Args:
        name: Name of the strategy to write to
        content: The Python code content to write to the strategy file

    Returns:
        Dictionary containing success confirmation or error message
    """
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD
    try:
        auth_token_hashed = hash_password(password)

        # Make authenticated request to save the strategy
        import requests
        response = requests.post(
            f'{api_url}/strategy/save',
            json={'name': name, 'content': content},
            headers={'Authorization': auth_token_hashed},  # Jesse uses token directly, not Bearer format
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                return {
                    "status": "success",
                    "action": "strategy_updated",
                    "strategy_name": name,
                    "message": f"Strategy '{name}' content updated successfully"
                }
            else:
                return {
                    "status": "error",
                    "action": "strategy_write_failed",
                    "strategy_name": name,
                    "error_type": "api_error",
                    "message": data.get('message', 'Unknown error')
                }
        elif response.status_code == 401:
            return {
                "status": "error",
                "action": "strategy_write_failed",
                "strategy_name": name,
                "error_type": "authentication_failed",
                "message": "Invalid password provided"
            }
        elif response.status_code == 404:
            return {
                "status": "error",
                "action": "strategy_write_failed",
                "strategy_name": name,
                "error_type": "strategy_not_found",
                "message": f"Strategy '{name}' not found"
            }
        else:
            return {
                "status": "error",
                "action": "strategy_write_failed",
                "strategy_name": name,
                "error_type": "http_error",
                "http_status": response.status_code,
                "message": response.text
            }

    except ValueError as e:
        return {
            "status": "error",
            "action": "strategy_write_failed",
            "strategy_name": name,
            "error_type": "configuration_error",
            "message": str(e)
        }
    except requests.exceptions.RequestException as e:
        return {
            "status": "error",
            "action": "strategy_write_failed",
            "strategy_name": name,
            "error_type": "connection_error",
            "message": f"Could not connect to Jesse API",
            "details": str(e)
        }


def save_strategy_report_service(strategy_name: str, filename: str, content: str, overwrite: bool = False) -> dict:
    """
    Save a Markdown report into a strategy's reports folder using Jesse's API.

    The API writes it on the Jesse host, so the returned `path` is relative to the Jesse
    project there, whichever machine the assistant runs on.

    Args:
        strategy_name: Name of the existing strategy the report belongs to
        filename: Bare Markdown file name, e.g. "BTCUSDT_sharpe_optimization_report.md"
        content: Full Markdown text of the report
        overwrite: Replace an existing report with the same name instead of failing

    Returns:
        Dictionary containing the saved path or an error message
    """
    failed = {
        "status": "error",
        "action": "strategy_report_save_failed",
        "strategy_name": strategy_name,
        "filename": filename,
    }
    # Status codes set by strategy_handler.save_report(), mapped to stable error types.
    error_types = {
        400: "invalid_request",
        403: "unsafe_report_path",
        404: "strategy_not_found",
        409: "report_exists",
    }
    try:
        response = requests.post(
            f'{mcp_config.JESSE_API_URL}/strategy/save-report',
            json={'name': strategy_name, 'filename': filename, 'content': content, 'overwrite': overwrite},
            headers={'Authorization': hash_password(mcp_config.JESSE_PASSWORD)},  # Jesse uses token directly, not Bearer format
            timeout=10
        )
    except requests.exceptions.RequestException as e:
        return {
            **failed,
            "error_type": "connection_error",
            "message": "Could not connect to Jesse API",
            "details": str(e)
        }

    if response.status_code == 401:
        return {**failed, "error_type": "authentication_failed", "message": "Invalid password provided"}

    try:
        data = response.json()
    except ValueError:
        data = {}

    if response.status_code == 200 and data.get('status') == 'success':
        return {
            "status": "success",
            "action": "strategy_report_saved",
            "strategy_name": strategy_name,
            "filename": filename,
            "path": data.get('path'),
            "overwritten": data.get('overwritten', False),
            "size_bytes": data.get('size_bytes'),
            "location": REPORT_LOCATION,
            "message": data.get('message', 'Report saved')
        }

    if response.status_code in error_types:
        return {**failed, "error_type": error_types[response.status_code], "message": data.get('message', response.text)}

    return {
        **failed,
        "error_type": "http_error",
        "http_status": response.status_code,
        "message": data.get('message', response.text)
    }
