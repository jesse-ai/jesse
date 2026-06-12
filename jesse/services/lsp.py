import os
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


def install_lsp_server() -> None:
    """
    Downloads and installs the Python Language Server from GitHub releases
    based on the current platform and architecture.
    """        
    # Define the target directory
    from jesse import JESSE_DIR
    
    target_dir = os.path.join(JESSE_DIR, 'lsp')
    
    #Update process
    # If the lsp directory exists(installed), check if an update is available, if so, delete the lsp directory and all its contents and re-install it
    if os.path.exists(target_dir):
        try:
            should_update_lsp = is_lsp_update_available() # Check if an update is available  

            if should_update_lsp:
                # Delete the lsp directory and all its contents
                shutil.rmtree(target_dir, ignore_errors=True)
                # Re-install the Python Language Server
                return install_lsp_server()
        except Exception as e:
            print(jh.color(f"Error checking for LSP update: {str(e)}", 'yellow'))
            pass
     
    #Normal installation process
    #Define the start script based on the platform
    start_script = None
    if platform.system().lower() == 'windows':
        start_script = os.path.join(target_dir, 'start.bat')
    else:
        start_script = os.path.join(target_dir, 'start.sh')
    
    
    # Skip if already exists 
    if os.path.exists(target_dir) and os.path.exists(start_script):
        if jh.is_debuggable('lsp_installer'):
            print(f"Python Language Server already exists at {target_dir}")
        return
    
    # If the start script does not exist, delete the lsp directory and all its contents and re-install it
    if not os.path.exists(start_script):
        try:
            #delete the lsp directory and all its contents
            shutil.rmtree(target_dir, ignore_errors=True)
        except Exception as e:
            pass    
        
    # Install the Python Language Server
    try:
        # Determine the platform-specific package name
        try:
            package_name = _get_platform_package_name()
        except Exception as e:
            raise Exception(f"Cannot determine platform package name: {str(e)}")
        
        print(f"Detected platform package: {package_name}")
        
        # Get the latest release
        global LSP_RELEASE_URL
        response = requests.get(LSP_RELEASE_URL, timeout=10)
        response.raise_for_status()
        
        release_data = response.json()
        
        # Find the appropriate asset for this platform
        download_url = None
        for asset in release_data.get('assets', []):
            if asset['name'] == package_name:
                download_url = asset['browser_download_url']
                break
        
        if not download_url:
            raise Exception(f"Package '{package_name}' not found in latest release")        
        
        print(f"Downloading Python Language Server from {download_url}...")
        
        # Download the package
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_file = os.path.join(temp_dir, package_name)
            extract_temp_dir = os.path.join(temp_dir, 'extracted')
            
            with requests.get(download_url, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(temp_file, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            
            # Extract to temporary directory first
            os.makedirs(extract_temp_dir, exist_ok=True)
            
            if package_name.endswith('.tar.gz'):
                with tarfile.open(temp_file, 'r:gz') as tar:
                    tar.extractall(extract_temp_dir)
            elif package_name.endswith('.zip'):
                with zipfile.ZipFile(temp_file, 'r') as zip_ref:
                    zip_ref.extractall(extract_temp_dir)
            
            # Flatten the directory structure
            # If there's a single top-level directory, move its contents up
            extracted_items = os.listdir(extract_temp_dir)
            
            if len(extracted_items) == 1 and os.path.isdir(os.path.join(extract_temp_dir, extracted_items[0])):
                # Single directory - move its contents
                source_dir = os.path.join(extract_temp_dir, extracted_items[0])
            else:
                # Multiple items at top level - use as is
                source_dir = extract_temp_dir
            
            # Create target directory and move contents
            os.makedirs(target_dir, exist_ok=True)
            
            for item in os.listdir(source_dir):
                source_path = os.path.join(source_dir, item)
                dest_path = os.path.join(target_dir, item)
                if os.path.isdir(source_path):
                    shutil.copytree(source_path, dest_path)
                else:
                    shutil.copy2(source_path, dest_path)
            
            # Save the lsp version to file
            lsp_version = release_data.get('tag_name', '').lstrip('v')
            _save_lsp_version(lsp_version)
            
            print(jh.color("✓ Python Language Server installed successfully", 'green'))
    
    except requests.RequestException as e:
        raise Exception(f"Failed to download LSP server: {str(e)}")
    except Exception as e:
        raise Exception(f"Error installing LSP server: {str(e)}")
        
        
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