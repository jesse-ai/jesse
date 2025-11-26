import os
import platform
import requests
import shutil
import tarfile
import zipfile
import tempfile
import json
import subprocess
import psutil
import uuid
import jesse.helpers as jh

#Global variable to store the LSP default port
LSP_DEFAULT_PORT = 9001

# Global variable to store/track the lsp process
LSP_PROCESS = None

# Global variable to store the LSP PID file
LSP_PID_FILE = os.path.join(os.path.dirname(__file__), "..", "lsp", "lsp.pid")


LSP_RELEASE_URL = "https://api.github.com/repos/jesse-ai/python-language-server/releases/latest"

def __get_platform_package_name() -> str:
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

def __save_lsp_version_to_database(lsp_version: str) -> None:
    """
    Saves the Python Language Server version to the database.
    """
    from jesse.models.Option import Option
    from jesse.services.db import database
    database.open_connection()
   
    try:
        # Get the existing config record
        config_option = Option.get(Option.type == 'config')
        config_data = json.loads(config_option.json)
        
        # Ensure editor section exists
        if 'editor' not in config_data:
            config_data['editor'] = {}
    
        # Add lsp_version to editor section
        config_data['editor']['lsp_version'] = lsp_version
        
        # Update the config record
        config_option.json = json.dumps(config_data)
        config_option.updated_at = jh.now(True)
        config_option.save()
        
    except Exception as e:
        raise Exception(f"Error saving LSP version: {str(e)}")
    finally:
        database.close_connection()

def __save_lsp_process_info_to_file(process: subprocess.Popen, file_path: str, port: int, lsp_uuid: str) -> None:
    # Save port and unique identifier to file
    try:
        data = {
            "port": port,
            "uuid": lsp_uuid
        }
        with open(file_path, "w") as f:
            json.dump(data, f)

    except Exception as e:
        print(jh.color(f"Error saving LSP info to file: {str(e)}", 'yellow'))
        pass

import psutil

def is_lsp_running() -> bool:
    global LSP_PID_FILE

    if not os.path.exists(LSP_PID_FILE):
        return False

    try:
        with open(LSP_PID_FILE, "r") as f:
            data = json.load(f)
            port = data.get("port")
            expected_uuid = data.get("uuid")

        if not port or not expected_uuid:
            return False

        # Check if port is actually listening
        try:
            for conn in psutil.net_connections(kind='tcp'):
                if conn.status == 'LISTEN' and conn.laddr.port == port:
                    return True
        except psutil.AccessDenied:
            # Fallback: try to connect to the port
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            try:
                result = sock.connect_ex(('127.0.0.1', port))
                sock.close()
                return result == 0  # Port is open
            except Exception:
                sock.close()
                return False

        return False
    except Exception as e:
        print(jh.color(f"Error checking LSP process: {e}", 'yellow'))
        return False

def terminate_previous_lsp():
    if not os.path.exists(LSP_PID_FILE):
        return

    try:
        with open(LSP_PID_FILE, "r") as f:
            data = json.load(f)
            port = data.get("port")

        # Find and terminate process listening on the port
        try:
            for conn in psutil.net_connections(kind='tcp'):
                if conn.status == 'LISTEN' and conn.laddr.port == port:
                    try:
                        p = psutil.Process(conn.pid)
                        print(f"Stopping LSP (PID {p.pid}) on port {port}...")
                        p.terminate()
                        try:
                            p.wait(timeout=5)
                        except psutil.TimeoutExpired:
                            p.kill()
                        break  # Only terminate one process
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
        except psutil.AccessDenied:
            print(jh.color("Warning: Cannot access network connections to terminate LSP", 'yellow'))

    except Exception as e:
        print(jh.color(f"Error terminating LSP: {e}", 'yellow'))
    finally:
        # Clean up PID file
        if os.path.exists(LSP_PID_FILE):
            os.remove(LSP_PID_FILE)


def is_lsp_update_available() -> bool:
    """
    Checks if an update is available for the Python Language Server.
    """
    from jesse.models.Option import Option
    from jesse.services.db import database
    database.open_connection()
    try:
        config_option = Option.get(Option.type == 'config')
        config_data = json.loads(config_option.json)
        lsp_version = config_data.get('editor', {}).get('lsp_version', '')
        
        # Get the latest version info 
        global LSP_RELEASE_URL
        response = requests.get(LSP_RELEASE_URL, timeout=10)
        response.raise_for_status()
        
        release_data = response.json()
        latest_version = release_data.get('tag_name', '').lstrip('v')
        
        # Compare the latest version with the current version using packaging library
        from packaging import version
        # If the current version is not set, return True
        if lsp_version == '':
            return False
        # If the latest version is greater than the current version, return True
        if version.parse(latest_version) > version.parse(lsp_version):
            return True
        else:
            return False
            
    except Exception as e:
        raise Exception(f"Error checking for LSP update: {str(e)}")
    finally:
        database.close_connection()

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
            package_name = __get_platform_package_name()
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
            
            #write the lsp version to database into config table
            lsp_version = release_data.get('tag_name', '').lstrip('v')
            __save_lsp_version_to_database(lsp_version)
            
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
    
    if is_lsp_running():
        print(jh.color("Previous Python Language Server is still running. Terminating it...", 'yellow'))
        terminate_previous_lsp()
    
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
    print(f"LSP WS started at ws://localhost:{port}/lsp")
    
    # Start the lsp process and return the handle
    try:
        import subprocess
        # Generate unique identifier for this LSP instance
        lsp_uuid = str(uuid.uuid4())

        with open(os.devnull, 'w') as devnull:
            # Set up environment with UUID for child process identification
            env = os.environ.copy()
            env['JESSE_LSP_UUID'] = lsp_uuid

            process = subprocess.Popen(
                [
                    start_script,
                    '--port', str(port),
                    '--bot-root', jesse_bot_root,
                    '--jesse-root', jesse_framework_parent
                ],
                stdout=devnull,  # redirect stdout to devnull to suppress LSP output
                stderr=devnull,  # redirect stderr to devnull to suppress LSP errors
                env=env,  # Pass UUID in environment
                shell=False  # since we are using array arguments, we need to set shell to False
            )
        LSP_PROCESS = process
        __save_lsp_process_info_to_file(process, LSP_PID_FILE, port, lsp_uuid)
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