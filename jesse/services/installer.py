from jesse.services.env import ENV_VALUES
import jesse.helpers as jh
import platform
import requests
import subprocess
import sys
import click


def _pip_install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])


def install(is_live_plugin_already_installed: bool, strict: bool):
    if is_live_plugin_already_installed:
        from jesse_live.version import __version__
        click.clear()
        print(f'Version "{__version__}" of the live-trade plugin is already installed.')
        if strict:
            txt = '\nIf you meant to update, first delete the existing version by running "pip uninstall jesse_live -y" and then run "jesse install-live" one more time.'
            print(jh.color(txt, 'yellow'))
        return

    if 'LICENSE_API_TOKEN' not in ENV_VALUES:
        if strict:
            print('ERROR: You need to set the LICENSE_API_TOKEN environment variable in your .env')
        return

    # if no value is set for LICENSE_API_TOKEN, then no need to continue
    if not ENV_VALUES['LICENSE_API_TOKEN']:
        if strict:
            print("No license API token set. Please set the LICENSE_API_TOKEN environment variable to continue. If you don't have one yet, create one at https://jesse.trade/user/api-tokens" )
        return
    else:
        access_token = ENV_VALUES['LICENSE_API_TOKEN']

    if platform.system() == 'Darwin':
        os_name = 'mac'
    elif platform.system() == 'Linux':
        os_name = 'linux'
    elif platform.system() == 'Windows':
        os_name = 'windows'
    else:
        raise NotImplementedError(f'Unsupported OS: "{platform.system()}"')

    is_64_bit = platform.machine().endswith('64')
    print('is_64_bit', is_64_bit)
    if not is_64_bit:
        raise NotImplementedError(f'Only 64-bit machines are supported')

    is_arm = platform.machine().startswith('arm')
    print('is_arm', is_arm)
    # arm versions of linux and windows are not supported
    if is_arm and (os_name in ['linux', 'windows']):
        raise NotImplementedError(f'ARM versions of {os_name} are not supported. If you need them, send a request to contact@jesse.trade')

    # format os_name to something acceptable for the API
    if os_name == 'mac':
        formatted_os_name = 'macOS - M1' if is_arm else 'macOS - Intel'
    elif os_name == 'linux':
        formatted_os_name = 'Linux - x86_64'
    # windows
    else:
        formatted_os_name = 'Windows 10 - 64 bit'

    from jesse.version import __version__ as jesse_version
    print('Downloading the latest version of the live-trade plugin...')
    url = 'https://jesse.trade/api/download-release'
    headers = {
        'Authorization': 'Bearer ' + access_token
    }
    response = requests.post(url, headers=headers, params={
        'os': formatted_os_name,
        'python_version': '{}.{}'.format(*jh.python_version()),
        'beta': True,
        'jesse_version': jesse_version
    })
    if response.status_code != 200:
        raise Exception('Error: ' + response.text)

    # store the downloaded file in 'storage/downloads' using the name of the downloaded file
    filename = response.headers['Content-Disposition'].split('=')[1]
    filepath = 'storage/' + filename
    with open(filepath, 'wb') as f:
        f.write(response.content)

    # The downloaded file is a whl file. Install it with pip
    print(f'Installing {filename}...')
    _pip_install(filepath)

    # remove the raw installation file
    subprocess.check_call(['rm', filepath])
