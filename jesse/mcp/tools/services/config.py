"""
Jesse Configuration Service Functions

This module contains the core configuration service functions used by Jesse's
MCP tools. These functions handle the actual API calls to Jesse's configuration
endpoints.

The functions are separated from the MCP tool wrappers to allow for better
code organization and reusability.
"""

from .auth import hash_password
import jesse.mcp.mcp_config as mcp_config

def get_config_service() -> dict:
    """
    Get the current Jesse configuration from the database.

    This loads the complete Jesse configuration that controls how
    backtests and live trading operate, using the same endpoint
    that the dashboard uses.

    Returns:
        Dictionary containing the current configuration with status
    """
    import json
    import requests

    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    # Generate auth token (SHA256 hash of password)
    auth_token_hashed = hash_password(password)

    try:
        # Call the config controller endpoint (same as dashboard)
        response = requests.post(
            f'{api_url}/config/get',
            json={'current_config': {}},  # Empty config to get defaults
            headers={'Authorization': auth_token_hashed},
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            return {
                'status': 'success',
                'config': data.get('data', {}),
                'message': 'Configuration loaded successfully'
            }
        elif response.status_code == 401:
            return {
                'status': 'error',
                'message': 'Authentication failed'
            }
        else:
            return {
                'status': 'error',
                'message': f'Failed to load config: {response.text}'
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
            'message': 'Failed to load configuration'
        }


def update_config_service(config: str) -> dict:
    """
    Update the Jesse configuration in the database.

    This saves the provided configuration to the database using the
    same endpoint that the dashboard uses for configuration updates.

    Args:
        config: JSON string of the complete configuration to save

    Returns:
        Success confirmation or error message
    """
    import json
    import requests

    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    # Generate auth token (SHA256 hash of password)
    auth_token_hashed = hash_password(password)

    try:
        # Parse the config JSON
        new_config = json.loads(config)

        # Call the config update endpoint (same as dashboard)
        response = requests.post(
            f'{api_url}/config/update',
            json={'current_config': new_config},
            headers={'Authorization': auth_token_hashed},
            timeout=10
        )

        if response.status_code == 200:
            return {
                'status': 'success',
                'message': 'Configuration updated successfully'
            }
        elif response.status_code == 401:
            return {
                'status': 'error',
                'message': 'Authentication failed'
            }
        else:
            return {
                'status': 'error',
                'message': f'Failed to update config: {response.text}'
            }

    except json.JSONDecodeError as e:
        return {
            'status': 'error',
            'error': 'Invalid JSON format',
            'details': str(e),
            'message': 'Failed to parse configuration JSON'
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
            'message': 'Failed to update configuration'
        }


def _get_config_section_service(section: str) -> dict:
    """
    Internal helper function to get a specific section of the Jesse configuration.

    This loads the complete Jesse configuration and extracts the requested section.
    Available sections include: backtest, live, optimization, analytics, editor, monte_carlo

    Args:
        section: The configuration section to retrieve (e.g., 'backtest', 'live', 'optimization')

    Returns:
        Dictionary containing the requested configuration section or error message
    """
    # First get the full config
    config_result = get_config_service()

    if config_result['status'] != 'success':
        return config_result

    full_config = config_result['config']

    # Extract the requested section from the data
    if 'data' in full_config and section in full_config['data']:
        return {
            'status': 'success',
            'section': section,
            'config': full_config['data'][section],
            'message': f'Configuration section "{section}" loaded successfully'
        }
    else:
        return {
            'status': 'error',
            'section': section,
            'message': f'Configuration section "{section}" not found',
            'available_sections': list(full_config.get('data', {}).keys()) if 'data' in full_config else []
        }


def get_backtest_config_service() -> dict:
    """
    Get the backtest configuration section.

    This is a convenience method that loads the backtest-specific configuration
    including exchange settings, logging preferences, and warmup candles.

    Returns:
        Dictionary containing the backtest configuration
    """
    return _get_config_section_service('backtest')


def get_live_config_service() -> dict:
    """
    Get the live trading configuration section.

    This loads the live trading configuration including exchange settings
    and notification preferences.

    Returns:
        Dictionary containing the live trading configuration
    """
    return _get_config_section_service('live')


def get_optimization_config_service() -> dict:
    """
    Get the optimization configuration section.

    This loads the optimization settings including CPU cores, trials,
    and objective function configuration.

    Returns:
        Dictionary containing the optimization configuration
    """
    return _get_config_section_service('optimization')