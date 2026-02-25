"""
MCP Server Lifecycle Management

This module manages the MCP server process lifecycle:
- Starts the MCP server as a subprocess with proper configuration
- Monitors server startup and handles errors
- Provides graceful shutdown functionality

The MCP server runs in a separate process, allowing it to operate independently
from the main Jesse application while sharing the same Python environment.

USAGE:
------
Called from CLI (cli.py) when Jesse starts: run_mcp_server(host, port)
Called on shutdown: terminate_mcp_server()
"""

import sys
import os
import signal
import jesse.helpers as jh


# Global variable to store the MCP process handle
MCP_PROCESS = None


def _signal_handler(signum, frame):
    """Handle termination signals to gracefully shut down the MCP server."""
    signal_name = signal.Signals(signum).name if hasattr(signal, 'Signals') else str(signum)
    print(f"\n🛑 Received {signal_name}, shutting down MCP server...")

    # Terminate MCP server
    terminate_mcp_server()

    print("👋 MCP server shutdown complete")
    sys.exit(0)

def run_mcp_server(jesse_host:str, jesse_port:int) -> None:
    """
    Start the Jesse MCP Server as a subprocess.
    
    Reads MCP_PORT from .env file or uses default (9002). Creates a subprocess
    running jesse.mcp.server with the provided host/port and API URL.
    
    Args:
        jesse_host: Host address for the Jesse API (e.g., "0.0.0.0")
        jesse_port: Port number for the Jesse API (e.g., 9000)
        
    Raises:
        Exception: If the server fails to start or exits immediately
    """
    global MCP_PROCESS
    
    # Check if the MCP server is already running
    if MCP_PROCESS and MCP_PROCESS.poll() is None:
        print(jh.color("MCP Server is already running", "yellow"))
        return
    
    # Update the MCP config
    import jesse.mcp.mcp_config as mcp_config
    
    # define the jesse api url
    mcp_config.JESSE_API_URL = f"http://{jesse_host}:{jesse_port}"
    
    # Read the MCP server port from the .env file, if not set, use the default port (9002)
    from jesse.services.env import ENV_VALUES
    if 'MCP_PORT' in ENV_VALUES:
        mcp_config.MCP_PORT = int(ENV_VALUES['MCP_PORT'])

    # Update the MCP URL
    mcp_config.MCP_URL = f"http://localhost:{mcp_config.MCP_PORT}/mcp"

    # Update the Jesse password, it is required for WebSocket authentication
    mcp_config.JESSE_PASSWORD = ENV_VALUES.get('PASSWORD', '')
    if not mcp_config.JESSE_PASSWORD:
        raise Exception("PASSWORD not found in .env file. Required for MCP WebSocket authentication.")

    # Start the MCP server in a separate process and return the process handle
    try:
        import subprocess
        with open(os.devnull, 'w') as devnull:
            process = subprocess.Popen(
                [
                    sys.executable, "-m",
                    "jesse.mcp.server",
                    "--port", str(mcp_config.MCP_PORT),
                    "--api_url", mcp_config.JESSE_API_URL,
                    "--password", mcp_config.JESSE_PASSWORD
                ],
                # Do not redirect stdout or stderr so MCP output/errors are visible in the terminal
                shell=False  # since we are using array arguments, we need to set shell to False
        )
        # Set the global MCP_PROCESS
        MCP_PROCESS = process
        
        # wait for 0.2 seconds to make sure the process is started
        import time
        time.sleep(0.2)
        if process.poll() is not None:
            out, err = process.communicate()
            print("STDOUT:", out)
            print("STDERR:", err)
            raise Exception(f"MCP server exited immediately with code {process.poll()}")
        
        # If we reach here, the MCP server started successfully
        print(jh.color("✓ MCP Server is running at " + mcp_config.MCP_URL, "green"))

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, _signal_handler)   # Ctrl+C
        signal.signal(signal.SIGTERM, _signal_handler)  # Termination signal

    except Exception as e:
        MCP_PROCESS = None
        raise Exception(f"Failed to start MCP server: {str(e)}")
    
def terminate_mcp_server():
    """
    Terminate the Jesse MCP Server process gracefully.
    
    Attempts graceful shutdown (terminate), then force kill if needed.
    Cleans up the global process handle on completion.
    """
    # Stop MCP server if running
    global MCP_PROCESS
    if MCP_PROCESS:
        try:
            print(jh.color("Stopping MCP Server...", 'yellow'))
            MCP_PROCESS.terminate()
            MCP_PROCESS.wait(timeout=5)
            print(jh.color("✓ MCP Server stopped", 'green'))
        except Exception as e:
            print(jh.color(f"⚠ Error stopping MCP: {str(e)}", 'yellow'))
            try:
                print(jh.color("Force killing MCP Server...", 'yellow'))
                MCP_PROCESS.kill()  # Force kill if terminate fails
            except Exception as e:
                print(jh.color(f"⚠ Error force killing MCP: {str(e)}", 'yellow'))
                pass
        finally:
            MCP_PROCESS = None
            print(jh.color("✓ MCP Server terminated", 'green'))