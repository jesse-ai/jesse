"""
Jesse Strategy Service Functions

This module contains the core strategy service functions used by Jesse's
MCP tools. These functions handle the actual API calls to Jesse's strategy
endpoints.

The functions are separated from the MCP tool wrappers to allow for better
code organization and reusability.
"""

from .auth import hash_password
import jesse.mcp.mcp_config as mcp_config


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