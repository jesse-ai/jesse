import os
import json
import select
import subprocess
import sys
import time
from contextlib import contextmanager
from typing import Callable, Iterator

import click
import platform
import requests
import shutil
import tarfile
import zipfile
import tempfile
import jesse.helpers as jh

#Global variable to store the LSP default port
LSP_DEFAULT_PORT = 9001

# Global variable to store/track the lsp process
LSP_PROCESS = None


LSP_RELEASE_URL = "https://api.github.com/repos/jesse-ai/python-language-server/releases/latest"

def _get_platform_package_name() -> str:
    """
    Determines the appropriate package name based on the current platform and architecture.
    
    Returns:
        str: Package name (e.g., 'darwin-arm64.tar.gz', 'linux-x64.tar.gz', 'win32-x64.zip')
    """
    system = platform.system().lower()
    machine = platform.machine().lower()
    
    # Normalize architecture names
    if machine in ('x86_64', 'amd64'):
        arch = 'x64'
    elif machine in ('aarch64', 'arm64'):
        arch = 'arm64'
    else:
        raise Exception(f"Unsupported architecture: {machine}")
    
    # Map system to package name format
    if system == 'darwin':  # macOS
        return f'darwin-{arch}.tar.gz'
    elif system == 'linux':
        return f'linux-{arch}.tar.gz'
    elif system == 'windows':
        # Windows packages only have x64 available
        return 'win32-x64.zip'
    else:
        raise Exception(f"Unsupported operating system: {system}")

def _save_lsp_version(lsp_version: str) -> None:
    """
    Saves the Python Language Server version to a file.
    """
    from jesse import JESSE_DIR
    version_file = os.path.join(JESSE_DIR, 'lsp', 'VERSION')
    with open(version_file, 'w') as f:
        f.write(lsp_version)

def _get_lsp_version() -> str:
    """
    Reads the Python Language Server version from a file.
    Returns empty string if file doesn't exist.
    """
    from jesse import JESSE_DIR
    version_file = os.path.join(JESSE_DIR, 'lsp', 'VERSION')
    if not os.path.exists(version_file):
        return ''
    with open(version_file, 'r') as f:
        return f.read().strip()

def _compare_versions(version1: str, version2: str) -> int:
    """
    Compares two semantic version strings.
    
    Args:
        version1: First version string (e.g., '1.2.3')
        version2: Second version string (e.g., '1.2.4')
    
    Returns:
        int: -1 if version1 < version2, 0 if equal, 1 if version1 > version2
    """
    def normalize_version(v: str) -> list:
        """Convert version string to list of integers for comparison."""
        parts = []
        for part in v.split('.'):
            try:
                parts.append(int(part))
            except ValueError:
                parts.append(0)
        return parts
    
    v1_parts = normalize_version(version1)
    v2_parts = normalize_version(version2)
    
    max_len = max(len(v1_parts), len(v2_parts))
    v1_parts.extend([0] * (max_len - len(v1_parts)))
    v2_parts.extend([0] * (max_len - len(v2_parts)))
    
    for i in range(max_len):
        if v1_parts[i] < v2_parts[i]:
            return -1
        elif v1_parts[i] > v2_parts[i]:
            return 1
    
    return 0

def is_lsp_update_available() -> bool:
    """
    Checks if an update is available for the Python Language Server.
    """
    try:
        # Get the current installed version
        lsp_version = _get_lsp_version()
        
        # If the current version is not set, return False
        if lsp_version == '':
            return False
        
        # Get the latest version info 
        global LSP_RELEASE_URL
        response = requests.get(LSP_RELEASE_URL, timeout=10)
        response.raise_for_status()
        
        release_data = response.json()
        latest_version = release_data.get('tag_name', '').lstrip('v')
        
        # Compare versions
        return _compare_versions(lsp_version, latest_version) < 0
            
    except Exception as e:
        raise Exception(f"Error checking for LSP update: {str(e)}")


class _SkipLSP(Exception):
    """Signal that startup should continue without the optional language server."""


@contextmanager
def _skip_key_reader(enabled: bool) -> Iterator[Callable[[], bool]]:
    """Read a single key without Enter, restoring terminal settings on every exit."""
    if not enabled or not sys.stdin.isatty():
        yield lambda: False
        return

    if os.name == 'nt':
        # These modules are platform-specific and cannot be imported unconditionally.
        import msvcrt

        def skip_pressed() -> bool:
            return msvcrt.kbhit() and msvcrt.getwch().lower() == 's'

        yield skip_pressed
    else:
        import termios
        import tty

        fd = sys.stdin.fileno()
        original = termios.tcgetattr(fd)
        try:
            # cbreak keeps Ctrl+C functional while allowing S without a newline.
            tty.setcbreak(fd)
            yield lambda: bool(select.select([fd], [], [], 0)[0]) and os.read(fd, 1).lower() == b's'
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, original)


def _download_lsp_file(url: str, destination: str, skip_pressed: Callable[[], bool]) -> None:
    """Keep stalled network I/O in a disposable process so skipping is immediate."""
    downloader = os.path.join(os.path.dirname(__file__), 'lsp_download.py')
    with subprocess.Popen(
        [sys.executable, downloader, url, destination],
        stdin=subprocess.DEVNULL,
    ) as process:
        try:
            while process.poll() is None:
                if skip_pressed():
                    raise _SkipLSP()
                # Poll often enough for responsive keys without busy-waiting.
                time.sleep(0.1)
            if process.returncode:
                raise Exception("Failed to download Python Language Server files")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    # Bound cleanup even if a child cannot shut down normally.
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def install_lsp_server(allow_skip: bool = False) -> bool:
    """Install/update the language server; return False when startup skips it."""
    from jesse import JESSE_DIR

    target_dir = os.path.join(JESSE_DIR, 'lsp')
    start_name = 'start.bat' if platform.system().lower() == 'windows' else 'start.sh'
    installed = os.path.isfile(os.path.join(target_dir, start_name))
    interactive = allow_skip and sys.stdin.isatty()
    if interactive:
        click.echo("Checking Python Language Server. Press S at any time while downloading to skip for this run.")
    elif allow_skip:
        click.echo("Checking Python Language Server. Use 'jesse run --skip-lsp' to skip it.")

    try:
        with _skip_key_reader(interactive) as skip_pressed, tempfile.TemporaryDirectory() as temp_dir:
            release_file = os.path.join(temp_dir, 'release.json')
            try:
                _download_lsp_file(LSP_RELEASE_URL, release_file, skip_pressed)
                with open(release_file) as f:
                    release_data = json.load(f)
            except _SkipLSP:
                raise
            except Exception:
                if installed:
                    click.echo(jh.color("Could not check for LSP updates. Using the installed version.", 'yellow'))
                    return True
                raise

            latest_version = release_data.get('tag_name', '').lstrip('v')
            current_version = _get_lsp_version()
            if installed and (not current_version or _compare_versions(current_version, latest_version) >= 0):
                return True

            package_name = _get_platform_package_name()
            click.echo(f"Detected platform package: {package_name}")
            download_url = next((asset['browser_download_url'] for asset in release_data.get('assets', [])
                                 if asset['name'] == package_name), None)
            if not download_url:
                raise Exception(f"Package '{package_name}' not found in latest release")

            click.echo(f"Downloading Python Language Server from {download_url}...")
            temp_file = os.path.join(temp_dir, package_name)
            _download_lsp_file(download_url, temp_file, skip_pressed)
            if skip_pressed():
                raise _SkipLSP()

            extract_dir = os.path.join(temp_dir, 'extracted')
            os.makedirs(extract_dir)
            if package_name.endswith('.tar.gz'):
                with tarfile.open(temp_file, 'r:gz') as tar:
                    tar.extractall(extract_dir)
            else:
                with zipfile.ZipFile(temp_file, 'r') as archive:
                    archive.extractall(extract_dir)

            extracted_items = os.listdir(extract_dir)
            if len(extracted_items) == 1 and os.path.isdir(os.path.join(extract_dir, extracted_items[0])):
                source_dir = os.path.join(extract_dir, extracted_items[0])
            else:
                source_dir = extract_dir
            if not os.path.isfile(os.path.join(source_dir, start_name)):
                raise Exception("Downloaded Python Language Server package has no start script")

            # Keep any working installation intact until the download and extraction succeed.
            # Key cancellation ends before publishing files into the installation directory.
            if skip_pressed():
                raise _SkipLSP()
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
            shutil.copytree(source_dir, target_dir)
            _save_lsp_version(latest_version)
            click.echo(jh.color("✓ Python Language Server installed successfully", 'green'))
            return True
    except _SkipLSP:
        click.echo("Skipping Python Language Server for this run. Editor code intelligence will be unavailable.")
        return False


def run_lsp_server():
    """
    Runs the Python Language Server.
    """
    global LSP_PROCESS
    
    if LSP_PROCESS:
        print(jh.color("Python Language Server is already running", 'yellow'))
        return
    
    from jesse import JESSE_DIR
    lsp_dir = os.path.join(JESSE_DIR, 'lsp')

    #Define the start script based on the platform
    start_script = None
    if platform.system().lower() == 'windows':
        start_script = os.path.join(lsp_dir, 'start.bat')
    else:
        start_script = os.path.join(lsp_dir, 'start.sh')
    

    if not os.path.exists(lsp_dir):
        raise Exception("LSP directory not found. Please re-install it first by restarting the jesse.")
    
    if not os.path.exists(start_script):
        raise Exception("Python Language Server start script not found. Please re-install it first by restarting the jesse.")

    # Get the port from the .env file
    from jesse.services.env import ENV_VALUES
    port = None
    if 'LSP_PORT' in ENV_VALUES:
        port = int(ENV_VALUES['LSP_PORT'])
    else:
        print(jh.color(f"LSP_PORT is not set in the .env file. Using default port {LSP_DEFAULT_PORT}", 'yellow'))
        port = LSP_DEFAULT_PORT
        
    # Get the workspace root (Jesse Bot root) (e.g., /home/king/jesse/jesse-ai-jesse-bot)
    jesse_bot_root = os.getcwd()
    
    # Get the parent directory of the Jesse framework (e.g., /home/king/jesse/jesse-ai/jesse)
    jesse_framework_parent = os.path.dirname(JESSE_DIR)  # /home/king/jesse/jesse-ai/jesse    
    
    print("Starting Python Language Server...")
    print(f"LSP WS started at ws://localhost:{port}/lsp\n")
    
    # Start the lsp process and return the handle
    try:
        import subprocess        
        with open(os.devnull, 'w') as devnull:
            process = subprocess.Popen(
                [
                    start_script,
                    '--port', str(port),
                    '--bot-root', jesse_bot_root,
                    '--jesse-root', jesse_framework_parent
                ],
                stdout=devnull,  # redirect stdout to devnull to suppress LSP output
                stderr=devnull,  # redirect stderr to devnull to suppress LSP errors
                shell=False  # since we are using array arguments, we need to set shell to False
            )
        LSP_PROCESS = process
        # wait for 0.2 seconds to make sure the process is started
        import time
        time.sleep(0.2)
        if process.poll() is not None:
            raise Exception(f"LSP server exited immediately with code {process.poll()}")
                           
    except Exception as e:
        LSP_PROCESS = None
        raise Exception(f"Failed to start LSP server: {str(e)}")
    
def terminate_lsp_server():
    """
    Terminates the Python Language Server.
    """
    # Stop LSP server if running
    global LSP_PROCESS
    if LSP_PROCESS:
        try:
            print(jh.color("Stopping Python Language Server...", 'yellow'))
            LSP_PROCESS.terminate()
            LSP_PROCESS.wait(timeout=5)
            print(jh.color("✓ Python Language Server stopped", 'green'))
        except Exception as e:
            print(jh.color(f"⚠ Error stopping LSP: {str(e)}", 'yellow'))
            try:
                print(jh.color("Force killing Python Language Server...", 'yellow'))
                LSP_PROCESS.kill()  # Force kill if terminate fails
            except:
                pass
        finally:
            LSP_PROCESS = None
            print(jh.color("✓ Python Language Server terminated", 'green'))