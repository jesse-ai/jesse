import os
import requests
import jesse.helpers as jh
from jesse.info import exchange_info, jesse_supported_timeframes, JESSE_API_URL


def get_general_info(has_live=False) -> dict:
    from jesse.version import __version__ as jesse_version
    system_info = {
        'jesse_version': jesse_version
    }
    plan_info = {'plan': 'guest'}
    limits = {}

    if has_live:
        from jesse.services.auth import get_access_token
        access_token = get_access_token()
        if not access_token:
            has_live = False

        # version info
        from jesse_live.version import __version__ as live_version
        system_info['live_plugin_version'] = live_version

        if access_token:
            # get the account plan info via the access_token
            try:
                response = requests.post(
                    JESSE_API_URL + '/v2/user-info',
                    headers={'Authorization': f'Bearer {access_token}'},
                    timeout=10
                )
                
                # Check if response is JSON
                content_type = response.headers.get('Content-Type', '')
                if 'application/json' not in content_type:
                    raise Exception(
                        f"Jesse API returned unexpected content type '{content_type}'. "
                        f"The service might be temporarily unavailable. Please try again later."
                    )
                
                if response.status_code != 200:
                    try:
                        error_message = response.json().get('message', 'Unknown error')
                    except:
                        error_message = f"Received status code {response.status_code}"
                    raise Exception(
                        f"Failed to get user info from Jesse API: {error_message}"
                    )
                
                plan_info = response.json()
                limits = plan_info['limits']
            except requests.exceptions.RequestException as e:
                raise Exception(
                    f"Failed to connect to Jesse API. The service might be temporarily unavailable. "
                    f"Error: {str(e)}"
                )
            except ValueError as e:
                raise Exception(
                    f"Jesse API returned invalid JSON response. The service might be temporarily unavailable. "
                    f"Error: {str(e)}"
                )

    strategies_path = os.getcwd() + "/strategies/"
    strategies = list(sorted([name for name in os.listdir(strategies_path) if os.path.isdir(strategies_path + name) and not name.startswith('.')]))
    if "__pycache__" in strategies:
        strategies.remove("__pycache__")

    system_info['python_version'] = '{}.{}'.format(*jh.python_version())
    system_info['operating_system'] = jh.get_os()
    system_info['cpu_cores'] = jh.cpu_cores_count()
    system_info['is_docker'] = jh.is_docker()

    update_info = {}

    try:
        response = requests.get('https://pypi.org/pypi/jesse/json', timeout=10)
        if response.status_code == 200 and 'application/json' in response.headers.get('Content-Type', ''):
            update_info['jesse_latest_version'] = response.json()['info']['version']
        else:
            raise ValueError("Invalid response from PyPI")
            
        response = requests.get(
            JESSE_API_URL + '/plugins/live/releases/info',
            timeout=10
        )
        if response.status_code == 200 and 'application/json' in response.headers.get('Content-Type', ''):
            update_info['jesse_live_latest_version'] = response.json()[0]['version']
        else:
            raise ValueError("Invalid response from Jesse API")
            
        update_info['is_update_info_available'] = True
    except Exception as e:
        update_info['is_update_info_available'] = False
        # Log the error for debugging purposes
        jh.debug(f"Failed to fetch update info: {str(e)}")

    res = {
        'exchanges': exchange_info,
        'strategies': strategies,
        'jesse_supported_timeframes': jesse_supported_timeframes,
        'has_live_plugin_installed': has_live,
        'system_info': system_info,
        'update_info': update_info,
        'plan': plan_info['plan'],
    }

    if has_live:
        res['limits'] = {
            'ip_limit': limits['ip_limit'],
            'live_trading_tabs': limits['live_trading_tabs'],
            'trading_routes': limits['trading_routes'],
            'data_routes': limits['data_routes'],
            'timeframes': limits['timeframes'],
            'exchanges': list(limits['exchanges'].keys()),
        }

    return res
