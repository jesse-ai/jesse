import hmac
import os
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from hashlib import sha256

import requests
import jesse.helpers as jh
from jesse.info import exchange_info, jesse_supported_timeframes, JESSE_API_URL, JESSE_API2_URL
from jesse.services.env import ENV_VALUES, is_dev_env


UPDATE_INFO_CACHE_SECONDS = 15 * 60


def _get_plan_info(access_token: str | None) -> tuple[dict, dict]:
    if not access_token:
        return {'plan': 'guest'}, {}

    try:
        response = requests.post(
            JESSE_API_URL + '/v2/user-info',
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10
        )

        content_type = response.headers.get('Content-Type', '')
        if 'application/json' not in content_type:
            raise Exception(
                f"Jesse API returned unexpected content type '{content_type}'. "
                f"The service might be temporarily unavailable. Please try again later."
            )

        if response.status_code != 200:
            try:
                error_message = response.json().get('message', 'Unknown error')
            except ValueError:
                error_message = f"Received status code {response.status_code}"
            raise Exception(
                f"Failed to get user info from Jesse API: {error_message}"
            )

        plan_info = response.json()
        return plan_info, plan_info['limits']
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


@lru_cache(maxsize=2)
def _get_update_info(_cache_bucket: int) -> dict:
    update_info = {}

    try:
        if is_dev_env():
            raise ValueError("jesse is running locally, so don't check for updates from pypi")

        response = requests.get('https://pypi.org/pypi/jesse/json', timeout=10)
        if response.status_code == 200 and 'application/json' in response.headers.get('Content-Type', ''):
            update_info['jesse_latest_version'] = response.json()['info']['version']
        else:
            raise ValueError("Invalid response from PyPI")

        response = requests.get(
            JESSE_API2_URL + '/plugins/live/releases/info',
            timeout=10
        )
        if response.status_code == 200 and 'application/json' in response.headers.get('Content-Type', ''):
            update_info['jesse_live_latest_version'] = response.json()[0]['version']
        else:
            raise ValueError("Invalid response from Jesse API")

        update_info['is_update_info_available'] = True
    except Exception as e:
        update_info['is_update_info_available'] = False
        jh.debug(f"Failed to fetch update info: {str(e)}")

    return update_info


def _get_bootstrap_context_id(access_token: str | None, jesse_version: str, live_version: str) -> str:
    payload = '\0'.join((access_token or 'guest', jesse_version, live_version))
    return hmac.new(
        ENV_VALUES['PASSWORD'].encode('utf-8'),
        payload.encode('utf-8'),
        sha256
    ).hexdigest()


def _get_live_plugin_info(has_live: bool, access_token: str | None) -> tuple[bool, str]:
    plugin_installed = False
    live_version = ''
    if has_live:
        try:
            from jesse_live.version import __version__ as live_version
            plugin_installed = True
        except ImportError:
            plugin_installed = False

    return plugin_installed, live_version


def _format_limits(limits: dict) -> dict:
    if not limits:
        return {}

    return {
        'ip_limit': limits.get('ip_limit'),
        'live_trading_tabs': limits.get('live_trading_tabs'),
        'trading_routes': limits.get('trading_routes'),
        'data_routes': limits.get('data_routes'),
        'timeframes': limits.get('timeframes'),
        'exchanges': list(limits.get('exchanges', {}).keys()),
    }


def get_local_general_info(has_live=False) -> dict:
    from jesse.services.auth import get_access_token
    from jesse.version import __version__ as jesse_version

    access_token = get_access_token()
    plugin_installed, live_version = _get_live_plugin_info(has_live, access_token)

    system_info = {
        'jesse_version': jesse_version,
        'python_version': '{}.{}'.format(*jh.python_version()),
        'operating_system': jh.get_os(),
        'cpu_cores': jh.cpu_cores_count(),
        'is_docker': jh.is_docker(),
    }
    if access_token and live_version:
        system_info['live_plugin_version'] = live_version

    strategies_path = os.getcwd() + "/strategies/"
    strategies = list(sorted([
        name for name in os.listdir(strategies_path)
        if os.path.isdir(strategies_path + name) and not name.startswith('.')
    ]))
    if "__pycache__" in strategies:
        strategies.remove("__pycache__")

    return {
        'exchanges': exchange_info,
        'strategies': strategies,
        'jesse_supported_timeframes': jesse_supported_timeframes,
        'has_live_plugin_installed': plugin_installed,
        'has_license_token': bool(access_token),
        'system_info': system_info,
        'bootstrap_context_id': _get_bootstrap_context_id(access_token, jesse_version, live_version),
    }


def get_external_general_info(has_live=False) -> dict:
    from jesse.services.auth import get_access_token
    from jesse.version import __version__ as jesse_version

    access_token = get_access_token()
    _, live_version = _get_live_plugin_info(has_live, access_token)

    cache_bucket = int(time.monotonic() // UPDATE_INFO_CACHE_SECONDS)
    with ThreadPoolExecutor(max_workers=2) as executor:
        plan_future = executor.submit(_get_plan_info, access_token)
        update_future = executor.submit(_get_update_info, cache_bucket)
        plan_info, limits = plan_future.result()
        update_info = update_future.result().copy()

    res = {
        'update_info': update_info,
        'plan': plan_info['plan'],
        'bootstrap_context_id': _get_bootstrap_context_id(access_token, jesse_version, live_version),
    }

    if limits:
        res['limits'] = _format_limits(limits)

    return res


def get_general_info(has_live=False) -> dict:
    return {
        **get_local_general_info(has_live),
        **get_external_general_info(has_live),
    }
