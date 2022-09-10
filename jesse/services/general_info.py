import os
import requests
import jesse.helpers as jh
from jesse.info import exchange_info, jesse_supported_timeframes


def get_general_info(has_live=False) -> dict:
    from jesse.version import __version__ as jesse_version
    system_info = {
        'jesse_version': jesse_version
    }

    if has_live:
        from jesse.services.auth import get_access_token
        access_token = get_access_token()
        if not access_token:
            has_live = False

        # version info
        from jesse_live.version import __version__ as live_version
        system_info['live_plugin_version'] = live_version

    strategies_path = os.getcwd() + "/strategies/"
    strategies = list(sorted([name for name in os.listdir(strategies_path) if os.path.isdir(strategies_path + name)]))

    system_info['python_version'] = '{}.{}'.format(*jh.python_version())
    system_info['operating_system'] = jh.get_os()
    system_info['cpu_cores'] = jh.cpu_cores_count()
    system_info['is_docker'] = jh.is_docker()

    update_info = {}

    try:
        response = requests.get('https://pypi.org/pypi/jesse/json')
        update_info['jesse_latest_version'] = response.json()['info']['version']
        response = requests.get('https://jesse.trade/api/plugins/live/releases/info')
        update_info['jesse_live_latest_version'] = response.json()[0]['version']
        update_info['is_update_info_available'] = True
    except Exception:
        update_info['is_update_info_available'] = False

    return {
        'exchanges': exchange_info,
        'strategies': strategies,
        'jesse_supported_timeframes': jesse_supported_timeframes,
        'has_live_plugin_installed': has_live,
        'system_info': system_info,
        'update_info': update_info
    }
